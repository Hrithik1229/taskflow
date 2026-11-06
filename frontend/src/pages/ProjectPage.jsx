import { useMemo, useState } from 'react'
import {
  NavLink,
  Outlet,
  useMatch,
  useNavigate,
  useParams,
} from 'react-router-dom'
import Avatar from '../components/Avatar'
import Badge from '../components/Badge'
import ConfirmDialog from '../components/ConfirmDialog'
import ErrorState from '../components/ErrorState'
import Modal from '../components/Modal'
import Skeleton from '../components/Skeleton'
import { useToast } from '../context/ToastContext.js'
import {
  getErrorMessage,
  updateProject,
  deleteProject,
} from '../features/projects/api'
import { useProject } from '../features/projects/hooks'

export default function ProjectPage() {
  const { projectId } = useParams()
  const { project, isLoading, error, reload, setProject } =
    useProject(projectId)
  const { showToast } = useToast()
  const navigate = useNavigate()
  const isNestedPage = Boolean(useMatch('/projects/:projectId/:section'))
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [formError, setFormError] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)

  const outletContext = useMemo(
    () => ({ project, refreshProject: reload, setProject }),
    [project, reload, setProject],
  )

  function openSettings() {
    setName(project.name)
    setDescription(project.description || '')
    setFormError('')
    setSettingsOpen(true)
  }

  async function saveSettings(event) {
    event.preventDefault()
    const normalizedName = name.trim()
    if (!normalizedName) {
      setFormError('Project name cannot be empty.')
      return
    }
    setIsSaving(true)
    setFormError('')
    try {
      const updated = await updateProject(project.id, {
        name: normalizedName,
        description: description.trim() || null,
      })
      setProject(updated)
      setSettingsOpen(false)
      showToast('Project settings updated.', 'success')
    } catch (requestError) {
      setFormError(
        getErrorMessage(requestError, 'Project settings could not be updated.'),
      )
    } finally {
      setIsSaving(false)
    }
  }

  async function confirmDelete() {
    setIsDeleting(true)
    try {
      await deleteProject(project.id)
      setDeleteOpen(false)
      showToast('Project deleted.', 'success')
      navigate('/dashboard', { replace: true })
    } catch (requestError) {
      showToast(
        getErrorMessage(requestError, 'Project could not be deleted.'),
        'error',
      )
      setDeleteOpen(false)
    } finally {
      setIsDeleting(false)
    }
  }

  if (isLoading && !project) {
    return (
      <div
        className="project-loading"
        role="status"
        aria-label="Loading project"
      >
        <Skeleton count={3} />
      </div>
    )
  }
  if (!project) {
    return (
      <ErrorState
        message={error || 'Project could not be loaded.'}
        onRetry={reload}
      />
    )
  }

  return (
    <div className="project-page">
      <header className="project-heading">
        <div className="project-heading-main">
          <Avatar name={project.name} size="large" />
          <div>
            <div className="project-title-line">
              <p className="eyebrow">PROJECT</p>
              <Badge tone={project.role === 'owner' ? 'blue' : 'neutral'}>
                {project.role}
              </Badge>
            </div>
            <h1>{project.name}</h1>
            <p>
              {project.description || 'No description yet.'}
              <span className="project-member-summary">
                {project.member_count}{' '}
                {project.member_count === 1 ? 'member' : 'members'}
              </span>
            </p>
          </div>
        </div>
        {project.role === 'owner' && (
          <div className="project-owner-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={openSettings}
            >
              Edit settings
            </button>
            <button
              className="danger-outline-button"
              type="button"
              onClick={() => setDeleteOpen(true)}
            >
              Delete project
            </button>
          </div>
        )}
      </header>

      {error && <ErrorState message={error} onRetry={reload} />}

      <nav className="project-tabs" aria-label="Project sections">
        <NavLink
          to={`/projects/${project.id}`}
          end
          className={({ isActive }) =>
            `project-tab${isActive ? ' project-tab--active' : ''}`
          }
        >
          Overview
        </NavLink>
        <NavLink
          to={`/projects/${project.id}/board`}
          className={({ isActive }) =>
            `project-tab${isActive ? ' project-tab--active' : ''}`
          }
        >
          Board
        </NavLink>
        <NavLink
          to={`/projects/${project.id}/members`}
          className={({ isActive }) =>
            `project-tab${isActive ? ' project-tab--active' : ''}`
          }
        >
          Members
        </NavLink>
      </nav>

      {isNestedPage ? (
        <Outlet context={outletContext} />
      ) : (
        <section className="project-overview">
          <h2>Project overview</h2>
          <p>Manage your collaborators from the Members section.</p>
          <NavLink
            className="secondary-button project-members-link"
            to={`/projects/${project.id}/members`}
          >
            View members
          </NavLink>
        </section>
      )}

      {settingsOpen && (
        <Modal title="Project settings" onClose={() => setSettingsOpen(false)}>
          <form className="project-form" onSubmit={saveSettings}>
            <div className="form-field">
              <label htmlFor="settings-project-name">Project name</label>
              <input
                id="settings-project-name"
                autoFocus
                maxLength={120}
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
              />
            </div>
            <div className="form-field">
              <label htmlFor="settings-project-description">Description</label>
              <textarea
                id="settings-project-description"
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
                onClick={() => setSettingsOpen(false)}
                disabled={isSaving}
              >
                Cancel
              </button>
              <button
                className="primary-button"
                type="submit"
                disabled={isSaving}
              >
                {isSaving ? 'Saving…' : 'Save changes'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {deleteOpen && (
        <ConfirmDialog
          title="Delete project?"
          message={`“${project.name}” and its associated project data will be permanently deleted.`}
          confirmLabel="Delete project"
          isDestructive
          isLoading={isDeleting}
          onClose={() => setDeleteOpen(false)}
          onConfirm={confirmDelete}
        />
      )}
    </div>
  )
}
