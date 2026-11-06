from uuid import uuid4

import pytest

from app.models import ProjectRole
from app.security.permissions import ProjectAction, can_perform

ROLE_ACTION_MATRIX = {
    ProjectAction.PROJECT_UPDATE: (True, False, False),
    ProjectAction.PROJECT_DELETE: (True, False, False),
    ProjectAction.MEMBER_ADD: (True, True, False),
    ProjectAction.MEMBER_CHANGE_ROLE: (True, False, False),
    ProjectAction.MEMBER_REMOVE: (True, True, False),
    ProjectAction.TASK_CREATE: (True, True, True),
    ProjectAction.TASK_EDIT: (True, True, False),
    ProjectAction.TASK_DELETE: (True, True, False),
    ProjectAction.TASK_MOVE: (True, True, True),
    ProjectAction.TASK_REVIEW_DECIDE: (True, True, True),
    ProjectAction.TASK_SET_REVIEWER: (True, True, True),
    ProjectAction.COMMENT_CREATE: (True, True, True),
    ProjectAction.ACTIVITY_VIEW: (True, True, True),
}
ROLES = (ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.MEMBER)


@pytest.mark.parametrize(
    ("action", "expected"),
    [(action, permissions) for action, permissions in ROLE_ACTION_MATRIX.items()],
)
@pytest.mark.parametrize(("role_index", "role"), list(enumerate(ROLES)))
def test_role_action_matrix(
    action: ProjectAction,
    expected: tuple[bool, bool, bool],
    role_index: int,
    role: ProjectRole,
) -> None:
    kwargs = {}
    if action == ProjectAction.MEMBER_ADD:
        kwargs["target_role"] = ProjectRole.MEMBER
    elif action == ProjectAction.MEMBER_CHANGE_ROLE:
        kwargs["target_role"] = ProjectRole.MEMBER
    elif action == ProjectAction.MEMBER_REMOVE:
        kwargs.update(
            target_role=ProjectRole.MEMBER,
            target_user_id=uuid4(),
            user_id=uuid4(),
        )
    elif action in {ProjectAction.TASK_EDIT, ProjectAction.TASK_DELETE}:
        kwargs.update(resource_owner_id=uuid4(), assignee_id=uuid4(), user_id=uuid4())
    elif action == ProjectAction.TASK_REVIEW_DECIDE:
        user_id = uuid4()
        kwargs.update(reviewer_id=user_id, user_id=user_id)
    elif action == ProjectAction.TASK_SET_REVIEWER:
        user_id = uuid4()
        kwargs.update(review_requested_by_id=user_id, user_id=user_id)

    assert can_perform(role, action, **kwargs) is expected[role_index]


def test_member_can_edit_or_delete_only_created_or_assigned_tasks() -> None:
    user_id = uuid4()
    other_user_id = uuid4()

    assert can_perform(
        ProjectRole.MEMBER,
        ProjectAction.TASK_EDIT,
        resource_owner_id=user_id,
        user_id=user_id,
    )
    assert can_perform(
        ProjectRole.MEMBER,
        ProjectAction.TASK_DELETE,
        assignee_id=user_id,
        user_id=user_id,
    )
    assert not can_perform(
        ProjectRole.MEMBER,
        ProjectAction.TASK_EDIT,
        resource_owner_id=other_user_id,
        assignee_id=other_user_id,
        user_id=user_id,
    )


def test_member_add_role_limits() -> None:
    assert can_perform(
        ProjectRole.OWNER,
        ProjectAction.MEMBER_ADD,
        target_role=ProjectRole.ADMIN,
    )
    assert not can_perform(
        ProjectRole.ADMIN,
        ProjectAction.MEMBER_ADD,
        target_role=ProjectRole.ADMIN,
    )
    assert not can_perform(
        ProjectRole.MEMBER,
        ProjectAction.MEMBER_ADD,
        target_role=ProjectRole.MEMBER,
    )


def test_member_remove_target_and_self_leave_rules() -> None:
    actor_id = uuid4()
    other_id = uuid4()

    assert can_perform(
        ProjectRole.ADMIN,
        ProjectAction.MEMBER_REMOVE,
        target_role=ProjectRole.MEMBER,
        target_user_id=other_id,
        user_id=actor_id,
    )
    assert not can_perform(
        ProjectRole.ADMIN,
        ProjectAction.MEMBER_REMOVE,
        target_role=ProjectRole.ADMIN,
        target_user_id=other_id,
        user_id=actor_id,
    )
    assert can_perform(
        ProjectRole.MEMBER,
        ProjectAction.MEMBER_REMOVE,
        target_role=ProjectRole.MEMBER,
        target_user_id=actor_id,
        user_id=actor_id,
    )
    assert not can_perform(
        ProjectRole.MEMBER,
        ProjectAction.MEMBER_REMOVE,
        target_role=ProjectRole.MEMBER,
        target_user_id=other_id,
        user_id=actor_id,
    )
    assert not can_perform(
        ProjectRole.OWNER,
        ProjectAction.MEMBER_REMOVE,
        target_role=ProjectRole.OWNER,
        target_user_id=actor_id,
        user_id=actor_id,
    )


def test_review_permissions_require_reviewer_or_submitter() -> None:
    reviewer_id = uuid4()
    submitter_id = uuid4()
    other_id = uuid4()

    assert can_perform(
        ProjectRole.MEMBER,
        ProjectAction.TASK_REVIEW_DECIDE,
        reviewer_id=reviewer_id,
        user_id=reviewer_id,
    )
    assert not can_perform(
        ProjectRole.MEMBER,
        ProjectAction.TASK_REVIEW_DECIDE,
        reviewer_id=reviewer_id,
        user_id=submitter_id,
    )
    assert not can_perform(
        ProjectRole.MEMBER,
        ProjectAction.TASK_REVIEW_DECIDE,
        reviewer_id=None,
        user_id=other_id,
    )
    assert can_perform(
        ProjectRole.MEMBER,
        ProjectAction.TASK_SET_REVIEWER,
        reviewer_id=reviewer_id,
        review_requested_by_id=submitter_id,
        user_id=submitter_id,
    )
    assert can_perform(
        ProjectRole.MEMBER,
        ProjectAction.TASK_SET_REVIEWER,
        reviewer_id=reviewer_id,
        review_requested_by_id=submitter_id,
        user_id=reviewer_id,
    )
    assert not can_perform(
        ProjectRole.MEMBER,
        ProjectAction.TASK_SET_REVIEWER,
        reviewer_id=reviewer_id,
        review_requested_by_id=submitter_id,
        user_id=other_id,
    )


@pytest.mark.parametrize(
    ("role", "action"),
    [
        ("not-a-role", ProjectAction.TASK_CREATE),
        (ProjectRole.MEMBER, "not-an-action"),
    ],
)
def test_unknown_role_or_action_is_denied(
    role: str | ProjectRole,
    action: str | ProjectAction,
) -> None:
    assert not can_perform(role, action)
