import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCorners,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  useNavigate,
  useOutletContext,
  useParams,
  useSearchParams,
} from 'react-router-dom'
import Avatar from '../components/Avatar'
import Badge from '../components/Badge'
import ConfirmDialog from '../components/ConfirmDialog'
import EmptyState from '../components/EmptyState'
import ErrorState from '../components/ErrorState'
import Modal from '../components/Modal'
import Skeleton from '../components/Skeleton'
import { useAuth } from '../context/AuthContext.js'
import { useToast } from '../context/ToastContext.js'
import {
  createTask,
  deleteTask,
  getTask,
  getTaskErrorMessage,
  listTasks,
  listProjectMembers,
  updateTask,
} from '../features/tasks/api'
import { applyTaskEvent } from '../features/tasks/realtime'
import { useTasks } from '../features/tasks/hooks'
import useProjectRealtime from '../hooks/useProjectRealtime'

const COLUMNS = [
  { id: 'todo', label: 'To do', color: 'slate' },
  { id: 'in_progress', label: 'In progress', color: 'blue' },
  { id: 'review', label: 'Review', color: 'purple' },
  { id: 'completed', label: 'Completed', color: 'green' },
]

function localDateTime(value) {
  if (!value) return ''
  const date = new Date(value)
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset())
  return date.toISOString().slice(0, 16)
}

function relativeTime(value) {
  const timestamp = new Date(value).getTime()
  if (!Number.isFinite(timestamp)) return ''
  const seconds = Math.round((timestamp - Date.now()) / 1000)
  const units = [
    ['year', 60 * 60 * 24 * 365],
    ['month', 60 * 60 * 24 * 30],
    ['day', 60 * 60 * 24],
    ['hour', 60 * 60],
    ['minute', 60],
  ]
  const [unit, secondsPerUnit] =
    units.find(([, duration]) => Math.abs(seconds) >= duration) || [
      'second',
      1,
    ]
  return new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(
    Math.round(seconds / secondsPerUnit),
    unit,
  )
}

function taskAttribution(task) {
  if (task.status === 'in_progress' && task.status_changed_by) {
    return {
      label: `Moved by ${task.status_changed_by.username}`,
      time: task.status_changed_at,
    }
  }
  if (task.status === 'review') {
    if (!task.reviewer && !task.review_requested_by) return null
    return {
      label: `Reviewer: ${task.reviewer?.username || '—'} · from ${task.review_requested_by?.username || '—'}`,
      time: task.status_changed_at,
    }
  }
  if (task.status === 'completed') {
    const name =
      task.completed_by?.username ||
      (task.completed_by_removed ? 'Former member' : null)
    if (!name) return null
    return {
      label: `Completed by ${name}`,
      time: task.completed_at,
    }
  }
  return null
}

function TaskCard({
  task,
  onOpen,
  isDragging = false,
  disabled = false,
  disabledMessage = '',
}) {
  const { attributes, listeners, setNodeRef, transform } = useDraggable({
    id: `task-${task.id}`,
    data: { task },
    disabled,
  })
  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
    : undefined
  const overdue =
    task.due_at &&
    new Date(task.due_at) < new Date() &&
    task.status !== 'completed'
  const attribution = taskAttribution(task)

  return (
    <article
      ref={setNodeRef}
      className={`task-card task-card--${task.priority}${isDragging ? ' task-card--dragging' : ''}`}
      data-priority={task.priority}
      style={style}
    >
      <div className="task-card-heading">
        <button
          className="task-card-open"
          type="button"
          onClick={() => onOpen(task)}
        >
          <span className="task-card-title">{task.title}</span>
        </button>
        {disabledMessage && (
          <span id={`drag-disabled-${task.id}`} className="sr-only">
            {disabledMessage}
          </span>
        )}
        <button
          className="task-drag-handle"
          type="button"
          aria-label={`Move task ${task.title}`}
          disabled={disabled}
          title={disabledMessage || 'Drag to reorder or move'}
          {...attributes}
          {...listeners}
          aria-describedby={[
            attributes['aria-describedby'],
            disabledMessage ? `drag-disabled-${task.id}` : null,
          ]
            .filter(Boolean)
            .join(' ')}
        >
          <span aria-hidden="true">⋮⋮</span>
        </button>
      </div>
      {attribution && (
        <p className="task-card-attribution">
          <span>{attribution.label}</span>
          {attribution.time && (
            <time
              dateTime={attribution.time}
              title={new Date(attribution.time).toLocaleString()}
            >
              {relativeTime(attribution.time)}
            </time>
          )}
        </p>
      )}
      {task.description && (
        <p className="task-card-desc">{task.description}</p>
      )}
      <div className="task-card-footer">
        <div className="task-card-meta">
          <Badge
            tone={
              task.priority === 'urgent'
                ? 'danger'
                : task.priority === 'high'
                  ? 'warning'
                  : task.priority === 'medium'
                    ? 'blue'
                    : 'neutral'
            }
          >
            {task.priority}
          </Badge>
          {task.due_at && (
            <time
              className={overdue ? 'task-due task-due--overdue' : 'task-due'}
              title={new Date(task.due_at).toLocaleString()}
            >
              📅 {new Date(task.due_at).toLocaleDateString(undefined, {
                month: 'short',
                day: 'numeric',
              })}
              {overdue ? ' (overdue)' : ''}
            </time>
          )}
        </div>
        {task.assignee && (
          <span className="task-card-assignee" title={`Assigned to ${task.assignee.username}`}>
            <Avatar name={task.assignee.username} size="small" />
            <span>{task.assignee.username}</span>
          </span>
        )}
      </div>
    </article>
  )
}

function TaskColumn({ column, tasks, onOpen, onCreate, canDecideReview }) {
  const { setNodeRef, isOver } = useDroppable({
    id: `column-${column.id}`,
    data: { status: column.id },
  })
  return (
    <section
      ref={setNodeRef}
      className={`board-column board-column--${column.id}${isOver ? ' board-column--over' : ''}`}
      aria-label={`${column.label} tasks`}
    >
      <header className="board-column-header">
        <span className={`column-status-indicator column-status-indicator--${column.color}`} aria-hidden="true" />
        <h2>{column.label}</h2>
        <span className="board-count">{tasks.length}</span>
        {column.id !== 'review' && (
          <button
            className="board-add-button"
            type="button"
            onClick={() => onCreate(column.id)}
            aria-label={`Add task to ${column.label}`}
            title={`Add task to ${column.label}`}
          >
            +
          </button>
        )}
      </header>
      <div className="board-column-tasks">
        {tasks.length ? (
          tasks.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              onOpen={onOpen}
              disabled={
                task.isMoving ||
                (task.status === 'review' && !canDecideReview(task))
              }
              disabledMessage={
                task.isMoving
                  ? 'This task is currently being moved.'
                  : task.status === 'review' && !canDecideReview(task)
                    ? 'Only the reviewer, project owner, or admin can move a task out of Review.'
                    : ''
              }
            />
          ))
        ) : (
          <div className="board-column-empty">
            <p>No tasks yet</p>
            <span>
              {column.id === 'review'
                ? 'Choose a reviewer when submitting a task'
                : 'Drop task here or click +'}
            </span>
          </div>
        )}
      </div>
    </section>
  )
}

export default function BoardPage() {
  const { projectId } = useParams()
  const { project, refreshProject } = useOutletContext()
  const navigate = useNavigate()
  const { user } = useAuth()
  const { showToast } = useToast()
  const [searchParams, setSearchParams] = useSearchParams()
  const [members, setMembers] = useState([])
  const [activeTask, setActiveTask] = useState(null)
  const [selectedTask, setSelectedTask] = useState(null)
  const [createStatus, setCreateStatus] = useState(null)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const [searchInput, setSearchInput] = useState(searchParams.get('q') || '')
  const [movingTaskId, setMovingTaskId] = useState(null)
  const [reviewMove, setReviewMove] = useState(null)
  const [reviewerChoice, setReviewerChoice] = useState('')
  const taskQueryIdRef = useRef(null)

  const paramsKey = searchParams.toString()
  const requestedTaskId = searchParams.get('task')
  const params = useMemo(() => {
    const values = Object.fromEntries(new URLSearchParams(paramsKey))
    delete values.task
    if (values.overdue === 'true') values.overdue = true
    return values
  }, [paramsKey])

  const { tasks, setTasks, isLoading, isRefreshing, error, reload, move } = useTasks(
    projectId,
    params,
  )
  const tasksRef = useRef(tasks)
  useEffect(() => {
    tasksRef.current = tasks
  }, [tasks])

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor),
  )

  const reloadMembers = useCallback(async () => {
    try {
      const result = await listProjectMembers(projectId)
      setMembers(result)
    } catch {
      // silently ignore if unmounted
    }
  }, [projectId])

  useEffect(() => {
    let active = true
    listProjectMembers(projectId)
      .then((result) => {
        if (active) setMembers(result)
      })
      .catch(() => {
        if (active) {
          showToast(
            'Project members could not be loaded for assignment.',
            'error',
          )
        }
      })
    return () => {
      active = false
    }
  }, [projectId, showToast])

  useEffect(() => {
    if (!requestedTaskId) {
      taskQueryIdRef.current = null
      return undefined
    }
    if (taskQueryIdRef.current === requestedTaskId) return undefined
    taskQueryIdRef.current = requestedTaskId

    let active = true
    const existing = tasksRef.current.find((task) => task.id === requestedTaskId)
    const request = existing
      ? Promise.resolve(existing)
      : getTask(requestedTaskId)
    request
      .then((task) => {
        if (active) {
          setFormError('')
          setSelectedTask(task)
        }
      })
      .catch((requestError) => {
        if (active) {
          showToast(
            getTaskErrorMessage(
              requestError,
              'The requested task could not be opened.',
            ),
            'error',
          )
        }
      })
    return () => {
      active = false
    }
  }, [requestedTaskId, showToast])

  const recoverBoard = useCallback(async () => {
    try {
      await Promise.all([reload(), reloadMembers(), refreshProject?.()])
    } catch {
      showToast('The project board could not be refreshed.', 'error')
    }
  }, [refreshProject, reload, reloadMembers, showToast])

  const applyRealtimeEvent = useCallback(
    (eventName, payload) => {
      const currentTasks = tasksRef.current
      if (eventName === 'member_changed') {
        void Promise.all([reloadMembers(), refreshProject?.()]).catch(() => {
          showToast('Project membership could not be refreshed.', 'error')
        })
        return
      }
      if (eventName === 'project_updated') {
        void refreshProject?.()
        return
      }
      if (eventName === 'project_deleted') {
        showToast('This project was deleted.', 'error')
        navigate('/dashboard', { replace: true })
        return
      }
      if (
        eventName === 'comment_added' ||
        eventName === 'notification_created'
      ) {
        return
      }
      if (paramsKey) {
        void reload()
        return
      }
      const result = applyTaskEvent(currentTasks, eventName, payload)
      if (result.shouldRefetch) {
        void reload()
      } else if (result.tasks !== currentTasks) {
        setTasks(result.tasks)
      }
    },
    [
      navigate,
      paramsKey,
      refreshProject,
      reload,
      reloadMembers,
      setTasks,
      showToast,
    ],
  )

  const handleRemoved = useCallback(() => {
    showToast('You were removed from this project.', 'error')
    navigate('/dashboard', { replace: true })
  }, [navigate, showToast])

  const realtime = useProjectRealtime(projectId, {
    onEvent: applyRealtimeEvent,
    onRemoved: handleRemoved,
    onRecover: recoverBoard,
  })

  // Debounced search sync
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const next = new URLSearchParams(searchParams)
      const normalized = searchInput.trim()
      if (normalized) next.set('q', normalized)
      else next.delete('q')
      if (next.toString() !== searchParams.toString()) {
        setSearchParams(next, { replace: true })
      }
    }, 250)
    return () => window.clearTimeout(timer)
  }, [searchInput, searchParams, setSearchParams])

  const grouped = useMemo(() => {
    const columns = Object.fromEntries(COLUMNS.map(({ id }) => [id, []]))
    tasks.forEach((task) => columns[task.status]?.push(task))
    Object.values(columns).forEach((items) =>
      items.sort((a, b) => a.position - b.position || a.id.localeCompare(b.id)),
    )
    return columns
  }, [tasks])

  const updateFilter = useCallback(
    (key, value) => {
      const next = new URLSearchParams(searchParams)
      if (value) next.set(key, value)
      else next.delete(key)
      setSearchParams(next, { replace: true })
    },
    [searchParams, setSearchParams],
  )

  const resetFilters = useCallback(() => {
    setSearchInput('')
    setSearchParams(new URLSearchParams(), { replace: true })
  }, [setSearchParams])

  function closeTaskDetails() {
    setSelectedTask(null)
    if (searchParams.has('task')) updateFilter('task', '')
  }

  const currentUserId = user?.id
  const isMyTasksActive = Boolean(
    currentUserId && searchParams.get('assigned_to') === currentUserId,
  )

  const toggleMyTasks = useCallback(() => {
    if (isMyTasksActive) {
      updateFilter('assigned_to', '')
    } else if (currentUserId) {
      updateFilter('assigned_to', currentUserId)
    }
  }, [currentUserId, isMyTasksActive, updateFilter])

  const canDecideReview = useCallback(
    (task) =>
      project?.role === 'owner' ||
      project?.role === 'admin' ||
      task.reviewer?.id === user?.id,
    [project?.role, user?.id],
  )

  const canEditSelected =
    project?.role === 'owner' ||
    project?.role === 'admin' ||
    selectedTask?.created_by === user?.id ||
    selectedTask?.assigned_to === user?.id

  const canChangeReviewer =
    selectedTask?.status === 'review' &&
    (project?.role === 'owner' ||
      project?.role === 'admin' ||
      selectedTask?.review_requested_by?.id === user?.id ||
      selectedTask?.reviewer?.id === user?.id)

  // Board statistics
  const stats = useMemo(() => {
    const total = tasks.length
    const completed = tasks.filter((t) => t.status === 'completed').length
    const urgent = tasks.filter((t) => t.priority === 'urgent' && t.status !== 'completed').length
    const completionPercent = total > 0 ? Math.round((completed / total) * 100) : 0
    return { total, completed, urgent, completionPercent }
  }, [tasks])

  function onDragStart(event) {
    setActiveTask(event.active.data.current?.task || null)
  }

  async function onDragEnd(event) {
    setActiveTask(null)
    const task = event.active.data.current?.task
    const overData = event.over?.data.current
    if (!task || !event.over) return
    let status = overData?.status
    let position
    if (event.over.id.toString().startsWith('task-')) {
      const targetId = event.over.id.toString().slice(5)
      const target = tasks.find((item) => item.id === targetId)
      if (!target) return
      status = target.status
      const targetColumn = grouped[status]
      const targetIndex = targetColumn.findIndex(
        (item) => item.id === target.id,
      )
      const movingBelow =
        (event.active.rect.current.translated?.top || 0) >
        event.over.rect.top + event.over.rect.height / 2
      const targetIndexAfterRemoval =
        task.status === status && task.position < target.position
          ? targetIndex - 1
          : targetIndex
      position = targetIndexAfterRemoval + (movingBelow ? 1 : 0)
    } else {
      position = grouped[status]?.length || 0
    }
    if (
      task.status === 'review' &&
      status !== 'review' &&
      status !== 'in_progress' &&
      status !== 'completed'
    ) {
      return
    }
    if (!status || (status === task.status && position === task.position))
      return
    if (status === 'review' && task.status !== 'review') {
      setReviewMove({ task, position })
      setReviewerChoice('')
      return
    }
    setMovingTaskId(task.id)
    try {
      await move(task, status, position)
    } catch (requestError) {
      showToast(
        getTaskErrorMessage(requestError, 'Task could not be moved.'),
        'error',
      )
    } finally {
      setMovingTaskId(null)
    }
  }

  async function confirmReviewMove(event) {
    event.preventDefault()
    if (!reviewMove || !reviewerChoice) return
    setMovingTaskId(reviewMove.task.id)
    try {
      await move(reviewMove.task, 'review', reviewMove.position, reviewerChoice)
      setReviewMove(null)
      setReviewerChoice('')
    } catch (requestError) {
      showToast(
        getTaskErrorMessage(requestError, 'Task could not be moved to Review.'),
        'error',
      )
      setReviewMove(null)
      setReviewerChoice('')
    } finally {
      setMovingTaskId(null)
    }
  }

  async function saveTask(event) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const title = String(form.get('title') || '').trim()
    if (!title) {
      setFormError('Task title is required.')
      return
    }
    setIsSaving(true)
    setFormError('')
    try {
      await createTask(projectId, {
        title,
        description: String(form.get('description') || '').trim() || null,
        priority: form.get('priority'),
        status: createStatus || 'todo',
        assigned_to: String(form.get('assigned_to') || '') || null,
        due_at: form.get('due_at')
          ? new Date(String(form.get('due_at'))).toISOString()
          : null,
      })
      setCreateStatus(null)
      await reload()
      showToast('Task created.', 'success')
    } catch (requestError) {
      setFormError(
        getTaskErrorMessage(requestError, 'Task could not be created.'),
      )
    } finally {
      setIsSaving(false)
    }
  }

  async function saveTaskDetails(event) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const title = String(form.get('title') || '').trim()
    if (!title) {
      setFormError('Task title is required.')
      return
    }
    setIsSaving(true)
    setFormError('')
    try {
      const payload = { expected_version: selectedTask.version }
      if (canEditSelected) {
        Object.assign(payload, {
          title,
          description: String(form.get('description') || '').trim() || null,
          priority: form.get('priority'),
          assigned_to: String(form.get('assigned_to') || '') || null,
          due_at: form.get('due_at')
            ? new Date(String(form.get('due_at'))).toISOString()
            : null,
        })
      }
      if (canChangeReviewer) {
        payload.reviewer_id =
          String(form.get('reviewer_id') || '') || null
      }
      const updated = await updateTask(selectedTask.id, payload)
      setSelectedTask(updated)
      await reload()
      showToast('Task updated.', 'success')
    } catch (requestError) {
      if (requestError?.response?.status === 409) {
        setFormError(
          'This task changed elsewhere. The latest version has been loaded; review and reapply your changes.',
        )
        await reload()
        const fresh = await listTasks(projectId, { limit: 500 })
        setSelectedTask(
          fresh.items.find((task) => task.id === selectedTask.id) ||
            selectedTask,
        )
      } else {
        setFormError(
          getTaskErrorMessage(requestError, 'Task could not be updated.'),
        )
      }
    } finally {
      setIsSaving(false)
    }
  }

  async function confirmDelete() {
    setIsSaving(true)
    try {
      await deleteTask(selectedTask.id)
      setDeleteOpen(false)
      setSelectedTask(null)
      await reload()
      showToast('Task deleted.', 'success')
    } catch (requestError) {
      showToast(
        getTaskErrorMessage(requestError, 'Task could not be deleted.'),
        'error',
      )
    } finally {
      setIsSaving(false)
    }
  }

  const canDeleteSelected = canEditSelected
  const eligibleReviewers = members.filter((member) => member.id !== user?.id)

  // Only show full skeleton loader on initial mount when there are no tasks yet
  if (isLoading && tasks.length === 0) {
    return (
      <div className="board-loading" role="status" aria-label="Loading board">
        <Skeleton count={4} />
      </div>
    )
  }
  if (error && tasks.length === 0) {
    return <ErrorState message={error} onRetry={reload} />
  }

  const hasActiveFilters = Boolean(
    searchInput ||
      searchParams.get('status') ||
      searchParams.get('priority') ||
      searchParams.get('assigned_to') ||
      searchParams.get('overdue') === 'true',
  )

  return (
    <div className="board-page">
      <header className="board-page-header">
        <div className="board-header-info">
          <div className="board-header-topline">
            <span className="eyebrow">PROJECT BOARD</span>
            <span
              className={`board-live-pill board-live-pill--${realtime.status}`}
              title={
                realtime.status === 'connected'
                  ? 'Real-time collaborative updates active'
                  : realtime.status === 'reconnecting'
                    ? 'Reconnecting live updates…'
                    : realtime.error || 'Live updates offline'
              }
            >
              <span className="live-dot" />
              <span>
                {realtime.status === 'connected'
                  ? 'Live'
                  : realtime.status === 'reconnecting'
                    ? 'Reconnecting'
                    : 'Offline'}
              </span>
            </span>
            {isRefreshing && (
              <span className="board-syncing-pill" aria-live="polite">
                <span className="board-sync-spinner" />
                <span>Syncing…</span>
              </span>
            )}
          </div>
          <h1>Tasks</h1>
          <p>Organize and track work in {project?.name || 'this project'}.</p>
        </div>

        <div className="board-header-actions">
          <button
            className="primary-button"
            type="button"
            onClick={() => setCreateStatus('todo')}
          >
            Create task
          </button>
        </div>
      </header>

      {/* Quick Metrics Bar */}
      <section className="board-stats-bar" aria-label="Board summary metrics">
        <div className="board-stat-item">
          <span className="board-stat-label">Total tasks</span>
          <span className="board-stat-value">{stats.total}</span>
        </div>
        <div className="board-stat-item">
          <span className="board-stat-label">Completed</span>
          <span className="board-stat-value">
            {stats.completed} <span className="board-stat-sub">({stats.completionPercent}%)</span>
          </span>
        </div>
        {stats.urgent > 0 && (
          <div className="board-stat-item board-stat-item--urgent">
            <span className="board-stat-label">Urgent</span>
            <span className="board-stat-value">{stats.urgent}</span>
          </div>
        )}
      </section>

      {/* Filter and Search Bar */}
      <section className="board-filters" aria-label="Task filters">
        <div className="board-search-field">
          <label htmlFor="board-search-input">Search tasks</label>
          <div className="board-search-box">
            <input
              id="board-search-input"
              type="search"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="Search title or description…"
            />
            {searchInput && (
              <button
                type="button"
                className="board-search-clear"
                onClick={() => setSearchInput('')}
                aria-label="Clear search text"
              >
                ×
              </button>
            )}
          </div>
        </div>

        <label>
          Priority
          <select
            value={searchParams.get('priority') || ''}
            onChange={(event) => updateFilter('priority', event.target.value)}
          >
            <option value="">All priorities</option>
            {['low', 'medium', 'high', 'urgent'].map((priority) => (
              <option key={priority} value={priority}>
                {priority.charAt(0).toUpperCase() + priority.slice(1)}
              </option>
            ))}
          </select>
        </label>

        <label>
          Assignee
          <select
            value={searchParams.get('assigned_to') || ''}
            onChange={(event) =>
              updateFilter('assigned_to', event.target.value)
            }
          >
            <option value="">All assignees</option>
            {members.map((member) => (
              <option key={member.id} value={member.id}>
                {member.username}
              </option>
            ))}
          </select>
        </label>

        {user?.id && (
          <button
            type="button"
            className={`board-my-tasks-button${isMyTasksActive ? ' board-my-tasks-button--active' : ''}`}
            onClick={toggleMyTasks}
          >
            👤 My tasks
          </button>
        )}

        <label className="board-overdue-filter">
          <input
            type="checkbox"
            checked={searchParams.get('overdue') === 'true'}
            onChange={(event) =>
              updateFilter('overdue', event.target.checked ? 'true' : '')
            }
          />
          Overdue only
        </label>

        {hasActiveFilters && (
          <button
            type="button"
            className="board-filter-reset"
            onClick={resetFilters}
          >
            ✕ Reset filters
          </button>
        )}
      </section>

      {tasks.length === 0 ? (
        <EmptyState
          title="No tasks match these filters"
          children="Try changing a filter, or create a task to get started."
          action={
            <button
              className="primary-button"
              type="button"
              onClick={() => setCreateStatus('todo')}
            >
              Create task
            </button>
          }
        />
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCorners}
          onDragStart={onDragStart}
          onDragEnd={onDragEnd}
          onDragCancel={() => setActiveTask(null)}
          accessibility={{
            announcements: {
              onDragStart: ({ active }) =>
                `Picked up ${active.data.current?.task?.title || 'task'}.`,
              onDragOver: ({ over }) =>
                over
                  ? `Task moved over ${over.data.current?.status || 'another task'}.`
                  : 'Task is not over a drop target.',
              onDragEnd: ({ active, over }) =>
                over
                  ? `Dropped ${active.data.current?.task?.title || 'task'}.`
                  : 'Task was not moved.',
            },
          }}
        >
          <div className="task-board">
            {COLUMNS.map((column) => (
              <TaskColumn
                key={column.id}
                column={column}
                tasks={grouped[column.id].map((task) => ({
                  ...task,
                  isMoving: movingTaskId === task.id,
                }))}
                onOpen={(task) => {
                  setFormError('')
                  setSelectedTask(task)
                }}
                onCreate={setCreateStatus}
                canDecideReview={canDecideReview}
              />
            ))}
          </div>
          <DragOverlay>
            {activeTask ? (
              <div className="task-card task-card--preview" aria-hidden="true">
                <span className="task-card-title">{activeTask.title}</span>
              </div>
            ) : null}
          </DragOverlay>
        </DndContext>
      )}

      {createStatus && (
        <Modal title="Create task" onClose={() => setCreateStatus(null)}>
          <form className="task-form" onSubmit={saveTask}>
            <TaskFields members={members} status={createStatus} />
            {formError && (
              <p className="form-server-error" role="alert">
                {formError}
              </p>
            )}
            <div className="modal-actions">
              <button
                className="secondary-button"
                type="button"
                onClick={() => setCreateStatus(null)}
                disabled={isSaving}
              >
                Cancel
              </button>
              <button
                className="primary-button"
                type="submit"
                disabled={isSaving}
              >
                {isSaving ? 'Creating…' : 'Create task'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {reviewMove && (
        <Modal
          title="Choose a reviewer"
          onClose={() => {
            setReviewMove(null)
            setReviewerChoice('')
          }}
        >
          <form className="task-form" onSubmit={confirmReviewMove}>
            <p>
              Choose a current project member to review “{reviewMove.task.title}”.
            </p>
            {eligibleReviewers.length ? (
              <div className="form-field">
                <label htmlFor="reviewer-choice">Reviewer</label>
                <select
                  id="reviewer-choice"
                  value={reviewerChoice}
                  onChange={(event) => setReviewerChoice(event.target.value)}
                  required
                >
                  <option value="">Choose a reviewer</option>
                  {eligibleReviewers.map((member) => (
                    <option key={member.id} value={member.id}>
                      {member.username}
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <p role="alert">
                No other current project member is available to review this task.
              </p>
            )}
            <div className="modal-actions">
              <button
                className="secondary-button"
                type="button"
                onClick={() => {
                  setReviewMove(null)
                  setReviewerChoice('')
                }}
              >
                Cancel
              </button>
              <button
                className="primary-button"
                type="submit"
                disabled={!reviewerChoice || isSaving || !eligibleReviewers.length}
              >
                Confirm review
              </button>
            </div>
          </form>
        </Modal>
      )}

      {selectedTask && (
        <Modal title="Task details" onClose={closeTaskDetails}>
          <form
            key={`${selectedTask.id}-${selectedTask.version}`}
            className="task-form"
            onSubmit={saveTaskDetails}
          >
            <StatusHistory task={selectedTask} />
            <TaskFields
              task={selectedTask}
              members={members}
              canEditTask={canEditSelected}
              canSetReviewer={canChangeReviewer}
            />
            {formError && (
              <p className="form-server-error" role="alert">
                {formError}
              </p>
            )}
            <div className="modal-actions task-detail-actions">
              {canDeleteSelected && (
                <button
                  className="danger-outline-button"
                  type="button"
                  onClick={() => setDeleteOpen(true)}
                >
                  Delete
                </button>
              )}
              <button
                className="secondary-button"
                type="button"
                onClick={closeTaskDetails}
                disabled={isSaving}
              >
                Close
              </button>
              <button
                className="primary-button"
                type="submit"
                disabled={isSaving || (!canEditSelected && !canChangeReviewer)}
              >
                {isSaving ? 'Saving…' : 'Save changes'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {deleteOpen && (
        <ConfirmDialog
          title="Delete task?"
          message={`“${selectedTask?.title}” will be permanently deleted.`}
          confirmLabel="Delete task"
          isDestructive
          isLoading={isSaving}
          onClose={() => setDeleteOpen(false)}
          onConfirm={confirmDelete}
        />
      )}
    </div>
  )
}

function StatusHistory({ task }) {
  const completedBy =
    task.completed_by?.username ||
    (task.completed_by_removed ? 'Former member' : '—')

  return (
    <section className="task-status-history" aria-labelledby="task-history-title">
      <h3 id="task-history-title">Status history</h3>
      <dl>
        <div>
          <dt>Moved by</dt>
          <dd>
            {task.status_changed_by?.username || '—'}
            {task.status_changed_at && (
              <time
                dateTime={task.status_changed_at}
                title={new Date(task.status_changed_at).toLocaleString()}
              >
                {relativeTime(task.status_changed_at)}
              </time>
            )}
          </dd>
        </div>
        {task.status === 'review' || task.reviewer || task.review_requested_by ? (
          <>
            <div>
              <dt>Reviewer</dt>
              <dd>{task.reviewer?.username || '—'}</dd>
            </div>
            <div>
              <dt>Submitted by</dt>
              <dd>{task.review_requested_by?.username || '—'}</dd>
            </div>
          </>
        ) : null}
        {task.status === 'completed' || task.completed_at ? (
          <div>
            <dt>Completed by</dt>
            <dd>
              {completedBy}
              {task.completed_at && (
                <time
                  dateTime={task.completed_at}
                  title={new Date(task.completed_at).toLocaleString()}
                >
                  {relativeTime(task.completed_at)}
                </time>
              )}
            </dd>
          </div>
        ) : null}
      </dl>
    </section>
  )
}

function TaskFields({
  task,
  members,
  status = 'todo',
  canEditTask = true,
  canSetReviewer = false,
}) {
  return (
    <>
      {task && !canEditTask && (
        <p className="task-field-permission">
          You can view this task, but only its creator, assignee, owner, or admin
          can edit its details.
        </p>
      )}
      <div className="form-field">
        <label htmlFor="task-title">Title</label>
        <input
          id="task-title"
          name="title"
          defaultValue={task?.title || ''}
          maxLength={200}
          placeholder="What needs to be done?"
          required
          disabled={!canEditTask}
        />
      </div>
      <div className="form-field">
        <label htmlFor="task-description">Description</label>
        <textarea
          id="task-description"
          name="description"
          defaultValue={task?.description || ''}
          maxLength={5000}
          rows={3}
          placeholder="Add details, acceptance criteria, or context…"
          disabled={!canEditTask}
        />
      </div>
      <div className="form-grid-row">
        <div className="form-field">
          <label htmlFor="task-priority">Priority</label>
          <select
            id="task-priority"
            name="priority"
            defaultValue={task?.priority || 'medium'}
            disabled={!canEditTask}
          >
            {['low', 'medium', 'high', 'urgent'].map((priority) => (
              <option key={priority} value={priority}>
                {priority.charAt(0).toUpperCase() + priority.slice(1)}
              </option>
            ))}
          </select>
        </div>
        <div className="form-field">
          <label htmlFor="task-assignee">Assignee</label>
          <select
            id="task-assignee"
            name="assigned_to"
            defaultValue={task?.assigned_to || ''}
            disabled={!canEditTask}
          >
            <option value="">Unassigned</option>
            {members.map((member) => (
              <option key={member.id} value={member.id}>
                {member.username}
              </option>
            ))}
          </select>
        </div>
      </div>
      {!task && <input type="hidden" name="status" value={status} />}
      {task?.status === 'review' &&
        (canSetReviewer ? (
          <div className="form-field">
            <label htmlFor="task-reviewer">Reviewer</label>
            <select
              id="task-reviewer"
              name="reviewer_id"
              defaultValue={task.reviewer_id || task.reviewer?.id || ''}
            >
              <option value="">No reviewer</option>
              {members
                .filter(
                  (member) => member.id !== task.review_requested_by?.id,
                )
                .map((member) => (
                  <option key={member.id} value={member.id}>
                    {member.username}
                  </option>
                ))}
            </select>
          </div>
        ) : (
          <p className="task-field-permission">
            The submitter, current reviewer, project owner, or admin can change
            the reviewer while this task is in Review.
          </p>
        ))}
      <div className="form-field">
        <label htmlFor="task-due-at">Due date</label>
        <input
          id="task-due-at"
          name="due_at"
          type="datetime-local"
          defaultValue={localDateTime(task?.due_at)}
          disabled={!canEditTask}
        />
      </div>
    </>
  )
}
