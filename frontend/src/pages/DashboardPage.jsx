import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.js'
import { useToast } from '../context/ToastContext.js'
import Badge from '../components/Badge'
import EmptyState from '../components/EmptyState'
import ErrorState from '../components/ErrorState'
import Modal from '../components/Modal'
import Skeleton from '../components/Skeleton'
import { getErrorMessage } from '../features/projects/api'
import { useProjects } from '../features/projects/hooks'
import * as taskApi from '../features/tasks/api'
import { useDashboardSummary } from '../features/tasks/hooks'

const ROLE_TONES = { owner: 'blue', admin: 'violet', member: 'neutral' }
const SUMMARY_METRICS = [
  { key: 'total', label: 'Total tasks', field: 'total_tasks', icon: '📋' },
  {
    key: 'assigned_to_me',
    label: 'Assigned to me',
    field: 'assigned_to_me',
    icon: '👤',
  },
  { key: 'overdue', label: 'Overdue', field: 'overdue', icon: '⏰' },
  { key: 'completed', label: 'Completed', field: 'completed', icon: '✅' },
]

export default function DashboardPage() {
  const { user } = useAuth()
  const { showToast } = useToast()
  const { projects, isLoading, error, reload, create } = useProjects()
  const {
    summary: taskSummary,
    isLoading: isSummaryLoading,
    error: summaryError,
    reload: reloadSummary,
  } = useDashboardSummary()
  const [createOpen, setCreateOpen] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [formError, setFormError] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [openMetric, setOpenMetric] = useState(null)
  const [breakdownState, setBreakdownState] = useState(null)
  const [breakdownRetry, setBreakdownRetry] = useState(0)
  const cardRefs = useRef({})

  const filteredProjects = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return projects
    return projects.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        (p.description && p.description.toLowerCase().includes(q)),
    )
  }, [projects, searchQuery])

  const currentBreakdownState =
    breakdownState?.metric === openMetric &&
    breakdownState?.summary === taskSummary &&
    breakdownState?.retry === breakdownRetry
      ? breakdownState
      : null
  const breakdown = currentBreakdownState?.result
  const breakdownError = currentBreakdownState?.error || ''
  const isBreakdownLoading = Boolean(openMetric && !currentBreakdownState)

  useEffect(() => {
    if (!openMetric) return undefined

    let active = true
    taskApi
      .getDashboardBreakdown(openMetric)
      .then((result) => {
        if (active) {
          setBreakdownState({
            metric: openMetric,
            summary: taskSummary,
            retry: breakdownRetry,
            result,
            error: '',
          })
        }
      })
      .catch((requestError) => {
        if (active) {
          setBreakdownState({
            metric: openMetric,
            summary: taskSummary,
            retry: breakdownRetry,
            result: null,
            error: taskApi.getTaskErrorMessage(
              requestError,
              'Task breakdown could not be loaded.',
            ),
          })
        }
      })

    return () => {
      active = false
    }
  }, [openMetric, taskSummary, breakdownRetry])

  useEffect(() => {
    if (!openMetric) return undefined
    function handleEscape(event) {
      if (event.key === 'Escape') {
        event.preventDefault()
        cardRefs.current[openMetric]?.focus()
        setOpenMetric(null)
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [openMetric])

  async function submitProject(event) {
    event.preventDefault()
    setFormError('')
    const normalizedName = name.trim()
    if (!normalizedName) {
      setFormError('Enter a project name.')
      return
    }
    if (normalizedName.length > 120 || description.length > 2000) {
      setFormError('Project name or description is too long.')
      return
    }
    setIsSubmitting(true)
    try {
      await create({
        name: normalizedName,
        description: description.trim() || null,
      })
      await reload()
      setCreateOpen(false)
      setName('')
      setDescription('')
      showToast('Project created.', 'success')
    } catch (requestError) {
      setFormError(
        getErrorMessage(requestError, 'The project could not be created.'),
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="dashboard-page">
      <section className="dashboard-welcome">
        <div>
          <p className="eyebrow">YOUR WORKSPACE</p>
          <h1>Welcome, {user?.username}</h1>
          <p>Bring your team’s work together in one place.</p>
        </div>
        <button
          className="primary-button"
          type="button"
          onClick={() => setCreateOpen(true)}
        >
          <span aria-hidden="true">+</span> Create project
        </button>
      </section>

      <section
        className="project-list-section"
        aria-labelledby="projects-heading"
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">YOUR TEAM SPACES</p>
            <h2 id="projects-heading">Projects</h2>
          </div>
          {!isLoading && !error && projects.length > 0 && (
            <div className="project-heading-actions">
              <input
                type="search"
                className="project-search-input"
                placeholder="Filter projects…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                aria-label="Filter projects"
              />
              <span className="muted-count">
                {filteredProjects.length === projects.length
                  ? `${projects.length} ${projects.length === 1 ? 'project' : 'projects'}`
                  : `${filteredProjects.length} of ${projects.length}`}
              </span>
            </div>
          )}
        </div>

        {isLoading ? (
          <Skeleton count={3} className="project-grid" />
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : projects.length === 0 ? (
          <EmptyState
            title="Your projects will show up here"
            action={
              <button
                className="primary-button"
                type="button"
                onClick={() => setCreateOpen(true)}
              >
                Create your first project
              </button>
            }
          >
            Create a project and invite your team to get started.
          </EmptyState>
        ) : filteredProjects.length === 0 ? (
          <div className="no-matches-card">
            <p>No projects match &ldquo;{searchQuery}&rdquo;</p>
            <button
              className="secondary-button"
              type="button"
              onClick={() => setSearchQuery('')}
            >
              Clear filter
            </button>
          </div>
        ) : (
          <div className="project-grid">
            {filteredProjects.map((project) => (
              <Link
                className="project-card"
                key={project.id}
                to={`/projects/${project.id}`}
              >
                <div className="project-card-top">
                  <span className="project-card-icon" aria-hidden="true">
                    {project.name.trim().slice(0, 1).toUpperCase()}
                  </span>
                  <span className="project-card-arrow" aria-hidden="true">
                    ↗
                  </span>
                </div>
                <h3>{project.name}</h3>
                <p className="project-card-description">
                  {project.description || 'No description yet.'}
                </p>
                <div className="project-card-footer">
                  <Badge tone={ROLE_TONES[project.role]}>{project.role}</Badge>
                  <span>
                    {project.member_count}{' '}
                    {project.member_count === 1 ? 'member' : 'members'}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>

      <section
        className="dashboard-task-summary"
        aria-labelledby="task-summary-heading"
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">ACROSS YOUR PROJECTS</p>
            <h2 id="task-summary-heading">Task summary</h2>
          </div>
        </div>
        {isSummaryLoading ? (
          <Skeleton count={4} className="task-summary-grid" />
        ) : summaryError ? (
          <div className="task-summary-error" role="alert">
            <p>{summaryError}</p>
            <button
              className="secondary-button"
              type="button"
              onClick={reloadSummary}
            >
              Try again
            </button>
          </div>
        ) : taskSummary ? (
          <div className="task-summary-grid">
            {SUMMARY_METRICS.map((metric) => (
              <SummaryItem
                key={metric.key}
                ref={(element) => {
                  cardRefs.current[metric.key] = element
                }}
                metric={metric}
                value={taskSummary[metric.field]}
                expanded={openMetric === metric.key}
                onClick={() => {
                  if (openMetric === metric.key) {
                    setOpenMetric(null)
                  } else {
                    setBreakdownRetry((attempt) => attempt + 1)
                    setOpenMetric(metric.key)
                  }
                }}
              />
            ))}
          </div>
        ) : null}
        <div
          id="dashboard-breakdown-panel"
          className="dashboard-breakdown-panel"
          hidden={!openMetric}
        >
          {openMetric && (
            <section aria-labelledby="dashboard-breakdown-title">
              <div className="dashboard-breakdown-heading">
                <h3 id="dashboard-breakdown-title">
                  {SUMMARY_METRICS.find((item) => item.key === openMetric)?.label}{' '}
                  by project
                </h3>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => {
                    cardRefs.current[openMetric]?.focus()
                    setOpenMetric(null)
                  }}
                >
                  Close
                </button>
              </div>
              {isBreakdownLoading ? (
                <Skeleton count={3} className="dashboard-breakdown-projects" />
              ) : breakdownError ? (
                <div className="dashboard-breakdown-error" role="alert">
                  <p>{breakdownError}</p>
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => setBreakdownRetry((attempt) => attempt + 1)}
                  >
                    Try again
                  </button>
                </div>
              ) : !breakdown?.projects?.length ? (
                <EmptyState title="No tasks in this category" />
              ) : (
                <div className="dashboard-breakdown-projects">
                  {breakdown.projects.map((projectBreakdown) => (
                    <article
                      className="dashboard-breakdown-project"
                      key={projectBreakdown.project_id}
                    >
                      <header>
                        <Link
                          to={`/projects/${projectBreakdown.project_id}/board`}
                        >
                          {projectBreakdown.project_name}
                        </Link>
                        <span>
                          {projectBreakdown.count}{' '}
                          {projectBreakdown.count === 1 ? 'task' : 'tasks'}
                        </span>
                      </header>
                      <ul>
                        {projectBreakdown.tasks.map((task) => {
                          const overdue =
                            task.due_at &&
                            new Date(task.due_at) < new Date() &&
                            task.status !== 'completed'
                          return (
                            <li key={task.id}>
                              <div className="dashboard-breakdown-task">
                                <Link
                                  to={`/projects/${projectBreakdown.project_id}/board?task=${task.id}`}
                                >
                                  {task.title}
                                </Link>
                                <div className="dashboard-breakdown-task-meta">
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
                                      className={
                                        overdue
                                          ? 'task-due task-due--overdue'
                                          : 'task-due'
                                      }
                                      dateTime={task.due_at}
                                      title={new Date(
                                        task.due_at,
                                      ).toLocaleString()}
                                    >
                                      {new Date(
                                        task.due_at,
                                      ).toLocaleDateString()}
                                    </time>
                                  )}
                                  <span className="dashboard-breakdown-status">
                                    {task.status.replace('_', ' ')}
                                  </span>
                                </div>
                                {task.status === 'completed' &&
                                  (task.completed_by ||
                                    task.completed_by_removed) && (
                                    <span className="dashboard-breakdown-completer">
                                      Completed by{' '}
                                      {task.completed_by?.username ||
                                        'Former member'}
                                    </span>
                                  )}
                              </div>
                            </li>
                          )
                        })}
                      </ul>
                      {projectBreakdown.has_more && (
                        <p className="dashboard-breakdown-more">
                          Showing the first 20 tasks.
                        </p>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </section>
          )}
        </div>
      </section>

      {createOpen && (
        <Modal title="Create a project" onClose={() => setCreateOpen(false)}>
          <form className="project-form" onSubmit={submitProject}>
            <div className="form-field">
              <label htmlFor="project-name">Project name</label>
              <input
                id="project-name"
                autoFocus
                maxLength={120}
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
              />
            </div>
            <div className="form-field">
              <label htmlFor="project-description">Description</label>
              <textarea
                id="project-description"
                maxLength={2000}
                rows={4}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </div>
            {formError && (
              <p className="form-server-error" role="alert">
                {formError}
              </p>
            )}
            <div className="modal-actions">
              <button
                className="secondary-button"
                type="button"
                onClick={() => setCreateOpen(false)}
                disabled={isSubmitting}
              >
                Cancel
              </button>
              <button
                className="primary-button"
                type="submit"
                disabled={isSubmitting}
              >
                {isSubmitting ? 'Creating…' : 'Create project'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}

function SummaryItem({ metric, value, expanded, onClick, ...props }) {
  return (
    <button
      {...props}
      className="task-summary-item"
      type="button"
      aria-label={`${metric.label}: ${value}. Show tasks by project`}
      aria-expanded={expanded}
      aria-controls="dashboard-breakdown-panel"
      onClick={onClick}
    >
      <div className="task-summary-item-header">
        <span>
          <span className="task-summary-item-label">{metric.label}</span>
        </span>
        {metric.icon && (
          <span className="task-summary-icon" aria-hidden="true">
            {metric.icon}
          </span>
        )}
      </div>
      <span className="task-summary-item-value">{value}</span>
    </button>
  )
}
