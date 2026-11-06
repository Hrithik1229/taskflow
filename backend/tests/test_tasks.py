import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.common.errors import TaskVersionConflict
from app.database import get_session
from app.main import fastapi_app
from app.models import (
    ActivityLog,
    Notification,
    Project,
    ProjectMember,
    ProjectRole,
    Task,
    TaskStatus,
    User,
)
from app.schemas.project import ProjectCreate
from app.schemas.task import TaskCreate, TaskMove, TaskUpdate
from app.security.jwt import create_access_token
from app.services.members import remove_member
from app.services.projects import create_project
from app.services.tasks import (
    create_task,
    dashboard_breakdown,
    dashboard_summary,
    delete_task,
    get_task,
    list_tasks,
    move_task,
    update_task,
)


@pytest_asyncio.fixture
async def task_client(session: AsyncSession):
    async def override_session():
        yield session

    fastapi_app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app),
            base_url="http://test",
        ) as client:
            yield client
    finally:
        fastapi_app.dependency_overrides.pop(get_session, None)


async def make_user(session: AsyncSession, label: str) -> User:
    suffix = uuid4().hex
    user = User(
        username=f"{label}-{suffix[:8]}",
        email=f"{label}-{suffix}@example.com",
        password_hash="not-used-in-these-tests",
    )
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_task_create_update_conflict_move_filters_and_outbox(
    session: AsyncSession,
) -> None:
    owner = await make_user(session, "task-owner")
    project, _ = await create_project(
        session,
        owner_id=owner.id,
        request=ProjectCreate(name="Tasks project"),
    )
    task, events = await create_task(
        session,
        project_id=project.id,
        actor_id=owner.id,
        request=TaskCreate(
            title="literal marker",
            description="contains %_ literally",
            assigned_to=owner.id,
        ),
        client_mutation_id="board-change-1",
    )
    second, _ = await create_task(
        session,
        project_id=project.id,
        actor_id=owner.id,
        request=TaskCreate(title="Another task"),
    )
    task_id = task.id
    second_id = second.id
    owner_id = owner.id
    owner_name = owner.username
    project_id = project.id

    assert task.position == 0
    assert task.version == 1
    assert events[0].payload["client_mutation_id"] == "board-change-1"
    assert events[0].payload["task_id"] == str(task.id)

    updated, _ = await update_task(
        session,
        task_id=task_id,
        user_id=owner_id,
        request=TaskUpdate(title="Updated title", expected_version=1),
    )
    assert updated.version == 2
    with pytest.raises(TaskVersionConflict) as conflict:
        await update_task(
            session,
            task_id=task_id,
            user_id=owner_id,
            request=TaskUpdate(title="Stale title", expected_version=1),
        )
    assert conflict.value.current.version == 2

    moved, _ = await move_task(
        session,
        task_id=task_id,
        user_id=owner_id,
        request=TaskMove(
            status=TaskStatus.COMPLETED,
            position=0,
            expected_version=2,
        ),
    )
    assert moved.task.status == TaskStatus.COMPLETED
    assert moved.task.position == 0
    assert moved.task.version == 3

    literal_search = await list_tasks(
        session,
        project_id=project_id,
        user_id=owner_id,
        query="%_",
    )
    assert [item.id for item in literal_search.items] == [task_id]
    completed = await list_tasks(
        session,
        project_id=project_id,
        user_id=owner_id,
        status_filter=TaskStatus.COMPLETED,
    )
    assert [item.id for item in completed.items] == [task_id]
    task_rows = list(
        (
            await session.scalars(
                select(Task)
                .where(Task.project_id == project_id, Task.status == TaskStatus.TODO)
                .order_by(Task.position)
            )
        ).all()
    )
    assert [(item.id, item.position) for item in task_rows] == [(second_id, 0)]

    read = await get_task(session, task_id=task_id, user_id=owner_id)
    assert read.creator.username == owner_name
    assert read.assignee.username == owner_name


@pytest.mark.asyncio
async def test_task_assignee_must_be_project_member_and_dashboard_counts(
    session: AsyncSession,
) -> None:
    owner = await make_user(session, "task-summary-owner")
    outsider = await make_user(session, "task-summary-outsider")
    project, _ = await create_project(
        session,
        owner_id=owner.id,
        request=ProjectCreate(name="Summary project"),
    )
    owner_id = owner.id
    outsider_id = outsider.id
    project_id = project.id
    with pytest.raises(HTTPException) as invalid_assignee:
        await create_task(
            session,
            project_id=project_id,
            actor_id=owner_id,
            request=TaskCreate(title="Invalid assignee", assigned_to=outsider_id),
        )
    assert invalid_assignee.value.status_code == 422

    await create_task(
        session,
        project_id=project_id,
        actor_id=owner_id,
        request=TaskCreate(
            title="Overdue assigned",
            assigned_to=owner_id,
            due_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )
    summary = await dashboard_summary(session, user_id=owner_id)
    assert summary.model_dump() == {
        "total_tasks": 1,
        "assigned_to_me": 1,
        "overdue": 1,
        "completed": 0,
    }

    outsider_membership = await session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == outsider_id,
        )
    )
    assert outsider_membership is None
    with pytest.raises(HTTPException) as hidden:
        await list_tasks(
            session,
            project_id=project_id,
            user_id=outsider_id,
        )
    assert hidden.value.status_code == 404


@pytest.mark.asyncio
async def test_dashboard_breakdowns_match_summary_and_hide_nonmember_projects(
    session: AsyncSession,
    task_client: AsyncClient,
) -> None:
    owner = await make_user(session, "breakdown-owner")
    outsider = await make_user(session, "breakdown-outsider")
    alpha, _ = await create_project(
        session,
        owner_id=owner.id,
        request=ProjectCreate(name="Alpha"),
    )
    beta, _ = await create_project(
        session,
        owner_id=owner.id,
        request=ProjectCreate(name="Beta"),
    )
    hidden_project, _ = await create_project(
        session,
        owner_id=outsider.id,
        request=ProjectCreate(name="Hidden"),
    )

    overdue_open, _ = await create_task(
        session,
        project_id=alpha.id,
        actor_id=owner.id,
        request=TaskCreate(
            title="Overdue open",
            assigned_to=owner.id,
            due_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )
    completed, _ = await create_task(
        session,
        project_id=alpha.id,
        actor_id=owner.id,
        request=TaskCreate(
            title="Overdue completed",
            assigned_to=owner.id,
            due_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )
    await move_task(
        session,
        task_id=completed.id,
        user_id=owner.id,
        request=TaskMove(
            status=TaskStatus.COMPLETED,
            position=0,
            expected_version=1,
        ),
    )
    await create_task(
        session,
        project_id=beta.id,
        actor_id=owner.id,
        request=TaskCreate(
            title="Future assigned",
            assigned_to=owner.id,
            due_at=datetime.now(UTC) + timedelta(days=1),
        ),
    )
    await create_task(
        session,
        project_id=beta.id,
        actor_id=owner.id,
        request=TaskCreate(title="Other task"),
    )
    await create_task(
        session,
        project_id=hidden_project.id,
        actor_id=outsider.id,
        request=TaskCreate(title="Must not leak"),
    )

    summary = await dashboard_summary(session, user_id=owner.id)
    expected_counts = {
        "total": summary.total_tasks,
        "overdue": summary.overdue,
        "completed": summary.completed,
        "assigned_to_me": summary.assigned_to_me,
    }
    for metric, expected_count in expected_counts.items():
        result = await dashboard_breakdown(
            session,
            user_id=owner.id,
            metric=metric,
        )
        assert result.total_count == expected_count
        assert sum(project.count for project in result.projects) == expected_count
        assert {project.project_id for project in result.projects} <= {
            alpha.id,
            beta.id,
        }
        assert all(project.count > 0 for project in result.projects)

    overdue_result = await dashboard_breakdown(
        session,
        user_id=owner.id,
        metric="overdue",
    )
    assert [
        task.id for project in overdue_result.projects for task in project.tasks
    ] == [overdue_open.id]
    completed_result = await dashboard_breakdown(
        session,
        user_id=owner.id,
        metric="completed",
    )
    completed_task = completed_result.projects[0].tasks[0]
    assert completed_task.completed_by.username == owner.username

    token = create_access_token(owner.id)
    unauthenticated = await task_client.get(
        "/api/dashboard/summary/breakdown?metric=total"
    )
    invalid_metric = await task_client.get(
        "/api/dashboard/summary/breakdown?metric=unknown",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert unauthenticated.status_code == 401
    assert invalid_metric.status_code == 422


@pytest.mark.asyncio
async def test_dashboard_breakdown_caps_tasks_but_keeps_exact_count(
    session: AsyncSession,
) -> None:
    owner = await make_user(session, "breakdown-cap-owner")
    project, _ = await create_project(
        session,
        owner_id=owner.id,
        request=ProjectCreate(name="Capped project"),
    )
    session.add_all(
        Task(
            project_id=project.id,
            title=f"Task {index:02}",
            created_by=owner.id,
            position=index,
        )
        for index in range(21)
    )
    await session.flush()

    breakdown = await dashboard_breakdown(
        session,
        user_id=owner.id,
        metric="total",
    )

    assert breakdown.total_count == 21
    assert len(breakdown.projects) == 1
    assert breakdown.projects[0].count == 21
    assert len(breakdown.projects[0].tasks) == 20
    assert breakdown.projects[0].has_more is True


@pytest.mark.asyncio
async def test_review_workflow_attributes_mover_and_credits_submitter(
    session: AsyncSession,
) -> None:
    owner = await make_user(session, "review-owner")
    submitter = await make_user(session, "review-submitter")
    reviewer = await make_user(session, "review-reviewer")
    replacement_reviewer = await make_user(session, "review-replacement")
    nonmember_reviewer = await make_user(session, "review-nonmember")
    project, _ = await create_project(
        session,
        owner_id=owner.id,
        request=ProjectCreate(name="Review workflow"),
    )
    session.add_all(
        ProjectMember(
            project_id=project.id,
            user_id=member.id,
            role=ProjectRole.MEMBER,
        )
        for member in (submitter, reviewer, replacement_reviewer)
    )
    await session.flush()
    owner_id = owner.id
    owner_name = owner.username
    submitter_id = submitter.id
    submitter_name = submitter.username
    reviewer_id = reviewer.id
    reviewer_name = reviewer.username
    replacement_reviewer_id = replacement_reviewer.id
    replacement_reviewer_name = replacement_reviewer.username
    nonmember_reviewer_id = nonmember_reviewer.id
    project_id = project.id

    task, _ = await create_task(
        session,
        project_id=project_id,
        actor_id=owner_id,
        request=TaskCreate(title="Review me"),
    )
    with pytest.raises(HTTPException) as missing_reviewer:
        await move_task(
            session,
            task_id=task.id,
            user_id=submitter_id,
            request=TaskMove(
                status=TaskStatus.REVIEW,
                position=0,
                expected_version=1,
            ),
        )
    assert missing_reviewer.value.status_code == 422
    with pytest.raises(HTTPException) as self_review:
        await move_task(
            session,
            task_id=task.id,
            user_id=submitter_id,
            request=TaskMove(
                status=TaskStatus.REVIEW,
                position=0,
                expected_version=1,
                reviewer_id=submitter_id,
            ),
        )
    assert self_review.value.status_code == 422
    with pytest.raises(HTTPException) as invalid_member:
        await move_task(
            session,
            task_id=task.id,
            user_id=submitter_id,
            request=TaskMove(
                status=TaskStatus.REVIEW,
                position=0,
                expected_version=1,
                reviewer_id=nonmember_reviewer_id,
            ),
        )
    assert invalid_member.value.status_code == 422

    submitted, submit_events = await move_task(
        session,
        task_id=task.id,
        user_id=submitter_id,
        request=TaskMove(
            status=TaskStatus.REVIEW,
            position=0,
            expected_version=1,
            reviewer_id=reviewer_id,
        ),
    )
    assert submitted.task.reviewer.username == reviewer_name
    assert submitted.task.review_requested_by.username == submitter_name
    assert submitted.task.status_changed_by.username == submitter_name
    assert any(
        event.event == "notification_created"
        and event.payload["notification"]["type"] == "review_requested"
        for event in submit_events
    )

    reassigned, reassignment_events = await update_task(
        session,
        task_id=task.id,
        user_id=submitter_id,
        request=TaskUpdate(
            reviewer_id=replacement_reviewer_id,
            expected_version=2,
        ),
    )
    assert reassigned.reviewer.username == replacement_reviewer_name
    assert any(
        event.event == "notification_created"
        and event.payload["notification"]["type"] == "review_requested"
        for event in reassignment_events
    )
    with pytest.raises(HTTPException) as review_to_todo:
        await move_task(
            session,
            task_id=task.id,
            user_id=replacement_reviewer_id,
            request=TaskMove(
                status=TaskStatus.TODO,
                position=0,
                expected_version=3,
            ),
        )
    assert review_to_todo.value.status_code == 422
    with pytest.raises(HTTPException) as submitter_cannot_decide:
        await move_task(
            session,
            task_id=task.id,
            user_id=submitter_id,
            request=TaskMove(
                status=TaskStatus.IN_PROGRESS,
                position=0,
                expected_version=3,
            ),
        )
    assert submitter_cannot_decide.value.status_code == 403

    completed, completion_events = await move_task(
        session,
        task_id=task.id,
        user_id=replacement_reviewer_id,
        request=TaskMove(
            status=TaskStatus.COMPLETED,
            position=0,
            expected_version=3,
        ),
    )
    assert completed.task.status_changed_by.username == replacement_reviewer_name
    assert completed.task.completed_by.username == submitter_name
    assert completed.task.completed_at is not None
    assert completed.task.reviewer.username == replacement_reviewer_name
    assert any(
        event.event == "notification_created"
        and event.payload["notification"]["type"] == "review_completed"
        for event in completion_events
    )
    completion_log = await session.scalar(
        select(ActivityLog).where(
            ActivityLog.entity_id == task.id,
            ActivityLog.action == "task.moved",
            ActivityLog.actor_id == replacement_reviewer_id,
        )
    )
    assert completion_log.details["mover"]["username"] == replacement_reviewer_name
    assert completion_log.details["credited_completer"]["username"] == submitter_name

    direct_task, _ = await create_task(
        session,
        project_id=project_id,
        actor_id=owner_id,
        request=TaskCreate(title="Direct completion"),
    )
    direct_completed, _ = await move_task(
        session,
        task_id=direct_task.id,
        user_id=owner_id,
        request=TaskMove(
            status=TaskStatus.COMPLETED,
            position=0,
            expected_version=1,
        ),
    )
    assert direct_completed.task.completed_by.username == owner_name
    reopened, _ = await move_task(
        session,
        task_id=direct_task.id,
        user_id=owner_id,
        request=TaskMove(
            status=TaskStatus.TODO,
            position=0,
            expected_version=2,
        ),
    )
    assert reopened.task.completed_by is None
    assert reopened.task.completed_at is None

    returned_task, _ = await create_task(
        session,
        project_id=project_id,
        actor_id=owner_id,
        request=TaskCreate(title="Needs changes"),
    )
    await move_task(
        session,
        task_id=returned_task.id,
        user_id=submitter_id,
        request=TaskMove(
            status=TaskStatus.REVIEW,
            position=0,
            expected_version=1,
            reviewer_id=reviewer_id,
        ),
    )
    returned, returned_events = await move_task(
        session,
        task_id=returned_task.id,
        user_id=reviewer_id,
        request=TaskMove(
            status=TaskStatus.IN_PROGRESS,
            position=0,
            expected_version=2,
        ),
    )
    assert returned.task.status_changed_by.username == reviewer_name
    assert returned.task.reviewer_id is None
    assert returned.task.review_requested_by is None
    assert any(
        event.event == "notification_created"
        and event.payload["notification"]["type"] == "changes_requested"
        for event in returned_events
    )

    with pytest.raises(HTTPException) as invalid_reviewer_edit:
        await update_task(
            session,
            task_id=returned_task.id,
            user_id=submitter_id,
            request=TaskUpdate(reviewer_id=reviewer_id, expected_version=3),
        )
    assert invalid_reviewer_edit.value.status_code == 422

    notification_count = await session.scalar(
        select(func.count(Notification.id)).where(Notification.project_id == project_id)
    )
    assert notification_count >= 3


@pytest.mark.asyncio
async def test_task_http_version_conflict_contains_current_state(
    session: AsyncSession,
    task_client: AsyncClient,
) -> None:
    owner = await make_user(session, "task-conflict-http")
    project, _ = await create_project(
        session,
        owner_id=owner.id,
        request=ProjectCreate(name="Conflict response project"),
    )
    task, _ = await create_task(
        session,
        project_id=project.id,
        actor_id=owner.id,
        request=TaskCreate(title="Current title"),
    )
    await update_task(
        session,
        task_id=task.id,
        user_id=owner.id,
        request=TaskUpdate(title="New title", expected_version=1),
    )

    response = await task_client.patch(
        f"/api/tasks/{task.id}",
        json={"title": "Stale title", "expected_version": 1},
        headers={"Authorization": f"Bearer {create_access_token(owner.id)}"},
    )
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "version_conflict"
    assert body["current"]["title"] == "New title"
    assert body["current"]["version"] == 2


@pytest.mark.asyncio
async def test_project_task_summary_returns_real_counts(
    session: AsyncSession,
) -> None:
    owner = await make_user(session, "project-task-summary")
    project, _ = await create_project(
        session,
        owner_id=owner.id,
        request=ProjectCreate(name="Project summary"),
    )
    await create_task(
        session,
        project_id=project.id,
        actor_id=owner.id,
        request=TaskCreate(
            title="Overdue",
            assigned_to=owner.id,
            due_at=datetime.now(UTC) - timedelta(hours=1),
        ),
    )
    from app.services.projects import get_project

    read = await get_project(session, project_id=project.id, user_id=owner.id)
    assert read.task_counts[TaskStatus.TODO] == 1
    assert read.overdue_task_count == 1
    assert read.assigned_to_me_count == 1
    assert await session.scalar(
        select(ActivityLog.id).where(
            ActivityLog.project_id == project.id,
            ActivityLog.action == "task.created",
        )
    )


@pytest.mark.asyncio
async def test_task_positions_remain_contiguous_after_reorder_move_and_delete(
    session: AsyncSession,
) -> None:
    owner = await make_user(session, "position-owner")
    reviewer = await make_user(session, "position-reviewer")
    project, _ = await create_project(
        session,
        owner_id=owner.id,
        request=ProjectCreate(name="Position project"),
    )
    session.add(
        ProjectMember(
            project_id=project.id,
            user_id=reviewer.id,
            role=ProjectRole.MEMBER,
        )
    )
    await session.flush()
    tasks = []
    for title in ("First", "Second", "Third"):
        task, _ = await create_task(
            session,
            project_id=project.id,
            actor_id=owner.id,
            request=TaskCreate(title=title),
        )
        tasks.append(task)

    moved_to_start, _ = await move_task(
        session,
        task_id=tasks[2].id,
        user_id=owner.id,
        request=TaskMove(
            status=TaskStatus.TODO,
            position=0,
            expected_version=1,
        ),
    )
    assert moved_to_start.task.position == 0
    assert {
        item.id: (item.position, item.version) for item in moved_to_start.affected
    } == {tasks[0].id: (1, 2), tasks[1].id: (2, 2)}

    moved_across, _ = await move_task(
        session,
        task_id=tasks[0].id,
        user_id=owner.id,
        request=TaskMove(
            status=TaskStatus.REVIEW,
            position=99,
            expected_version=2,
            reviewer_id=reviewer.id,
        ),
    )
    assert moved_across.task.position == 0
    assert moved_across.task.status == TaskStatus.REVIEW
    assert sorted(item.position for item in moved_across.affected) == [1]

    deleted_events = await delete_task(
        session,
        task_id=tasks[2].id,
        user_id=owner.id,
        client_mutation_id="delete-third",
    )
    assert deleted_events[0].payload["task"]["version"] == 3
    assert deleted_events[0].payload["client_mutation_id"] == "delete-third"
    assert deleted_events[0].payload["affected"] == [
        {"id": str(tasks[1].id), "position": 0, "version": 4}
    ]
    remaining = (
        await session.execute(
            select(Task.status, Task.position)
            .where(Task.project_id == project.id)
            .order_by(Task.status, Task.position)
        )
    ).all()
    assert set(remaining) == {(TaskStatus.TODO, 0), (TaskStatus.REVIEW, 0)}


@pytest.mark.asyncio
async def test_removing_member_unassigns_tasks_and_increments_versions(
    session: AsyncSession,
) -> None:
    owner = await make_user(session, "remove-task-owner")
    member = await make_user(session, "remove-task-member")
    project, _ = await create_project(
        session,
        owner_id=owner.id,
        request=ProjectCreate(name="Member task project"),
    )
    membership = ProjectMember(
        project_id=project.id,
        user_id=member.id,
        role=ProjectRole.MEMBER,
    )
    session.add(membership)
    await session.flush()
    review_task, _ = await create_task(
        session,
        project_id=project.id,
        actor_id=owner.id,
        request=TaskCreate(
            title="Reviewer before removal",
            assigned_to=member.id,
        ),
    )
    await move_task(
        session,
        task_id=review_task.id,
        user_id=owner.id,
        request=TaskMove(
            status=TaskStatus.REVIEW,
            position=0,
            expected_version=1,
            reviewer_id=member.id,
        ),
    )
    completed_task, _ = await create_task(
        session,
        project_id=project.id,
        actor_id=owner.id,
        request=TaskCreate(title="Completer before removal", assigned_to=member.id),
    )
    await move_task(
        session,
        task_id=completed_task.id,
        user_id=member.id,
        request=TaskMove(
            status=TaskStatus.COMPLETED,
            position=0,
            expected_version=1,
        ),
    )

    events = await remove_member(
        session,
        membership=await session.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == owner.id,
            )
        ),
        actor_id=owner.id,
        target_user_id=member.id,
    )
    assert events[0].payload["action"] == "member.removed"
    review_task_state = (
        await session.execute(
            select(
                Task.assigned_to,
                Task.reviewer_id,
                Task.version,
            ).where(Task.id == review_task.id)
        )
    ).one()
    assert review_task_state == (None, None, 3)
    completed_state = (
        await session.execute(
            select(
                Task.assigned_to,
                Task.completed_by,
                Task.completed_at,
                Task.version,
            ).where(Task.id == completed_task.id)
        )
    ).one()
    assert completed_state.assigned_to is None
    assert completed_state.completed_by is None
    assert completed_state.completed_at is not None
    assert completed_state.version == 3
    assert await session.scalar(
        select(ActivityLog.id).where(
            ActivityLog.entity_id == review_task.id,
            ActivityLog.action == "task.unassigned",
        )
    )
    assert await session.scalar(
        select(ActivityLog.id).where(
            ActivityLog.entity_id == review_task.id,
            ActivityLog.action == "task.reviewer_removed",
        )
    )
    assert await session.scalar(
        select(ActivityLog.id).where(
            ActivityLog.entity_id == completed_task.id,
            ActivityLog.action == "task.completion_credit_removed",
        )
    )
    task_events = [event for event in events if event.event == "task_changed"]
    assert len(task_events) == 2
    completed_event = next(
        event
        for event in task_events
        if event.payload["task_id"] == str(completed_task.id)
    )
    assert completed_event.payload["task"]["completed_by"] is None
    assert completed_event.payload["task"]["completed_by_removed"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["update", "move"])
@pytest.mark.parametrize("iteration", range(10))
async def test_concurrent_task_mutations_have_one_winner(
    test_engine,
    operation: str,
    iteration: int,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    owner = await make_user_in_committed_session(
        factory, f"race-{operation}-{iteration}"
    )
    project_id = None
    try:
        async with factory() as setup_session:
            project, _ = await create_project(
                setup_session,
                owner_id=owner.id,
                request=ProjectCreate(name=f"Concurrency {operation} {iteration}"),
            )
            project_id = project.id
            task, _ = await create_task(
                setup_session,
                project_id=project_id,
                actor_id=owner.id,
                request=TaskCreate(title="Concurrent task"),
            )

        async def change_title():
            async with factory() as mutation_session:
                return await update_task(
                    mutation_session,
                    task_id=task.id,
                    user_id=owner.id,
                    request=TaskUpdate(
                        title="Concurrent title",
                        expected_version=1,
                    ),
                )

        async def move_to_in_progress():
            async with factory() as mutation_session:
                return await move_task(
                    mutation_session,
                    task_id=task.id,
                    user_id=owner.id,
                    request=TaskMove(
                        status=TaskStatus.IN_PROGRESS,
                        position=0,
                        expected_version=1,
                    ),
                )

        operation_pair = (
            (change_title, change_title)
            if operation == "update"
            else (change_title, move_to_in_progress)
        )
        results = await asyncio.gather(
            *(call() for call in operation_pair),
            return_exceptions=True,
        )
        assert (
            sum(not isinstance(result, TaskVersionConflict) for result in results) == 1
        )
        assert sum(isinstance(result, TaskVersionConflict) for result in results) == 1
        async with factory() as verify_session:
            current_version = await verify_session.scalar(
                select(Task.version).where(Task.id == task.id)
            )
        assert current_version == 2
    finally:
        async with factory() as cleanup_session:
            if project_id is not None:
                project_to_remove = await cleanup_session.get(Project, project_id)
                if project_to_remove is not None:
                    await cleanup_session.delete(project_to_remove)
            owner_to_remove = await cleanup_session.get(User, owner.id)
            if owner_to_remove is not None:
                await cleanup_session.delete(owner_to_remove)
            await cleanup_session.commit()


async def make_user_in_committed_session(factory, label: str) -> User:
    async with factory() as setup_session:
        owner = await make_user(setup_session, label)
        await setup_session.commit()
        return owner
