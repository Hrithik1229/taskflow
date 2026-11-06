import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useOutletContext, useParams } from 'react-router-dom'
import Avatar from '../components/Avatar'
import Badge from '../components/Badge'
import ConfirmDialog from '../components/ConfirmDialog'
import EmptyState from '../components/EmptyState'
import ErrorState from '../components/ErrorState'
import Skeleton from '../components/Skeleton'
import { useAuth } from '../context/AuthContext.js'
import { useToast } from '../context/ToastContext.js'
import {
  addMember,
  getErrorMessage,
  listMembers,
  removeMember,
  updateMemberRole,
} from '../features/projects/api'

const ROLE_TONES = { owner: 'blue', admin: 'violet', member: 'neutral' }

export default function MembersPage() {
  const { project, refreshProject } = useOutletContext()
  const { projectId } = useParams()
  const { user } = useAuth()
  const { showToast } = useToast()
  const navigate = useNavigate()
  const [members, setMembers] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('member')
  const [formError, setFormError] = useState('')
  const [isAdding, setIsAdding] = useState(false)
  const [selectedRoles, setSelectedRoles] = useState({})
  const [pendingMember, setPendingMember] = useState(null)
  const [isRemoving, setIsRemoving] = useState(false)

  const reload = useCallback(async () => {
    setIsLoading(true)
    setLoadError('')
    try {
      setMembers(await listMembers(projectId))
    } catch (requestError) {
      setLoadError(
        getErrorMessage(requestError, 'Project members could not be loaded.'),
      )
    } finally {
      setIsLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    let active = true
    listMembers(projectId)
      .then((result) => {
        if (active) {
          setMembers(result)
        }
      })
      .catch((requestError) => {
        if (active) {
          setLoadError(
            getErrorMessage(
              requestError,
              'Project members could not be loaded.',
            ),
          )
        }
      })
      .finally(() => {
        if (active) {
          setIsLoading(false)
        }
      })
    return () => {
      active = false
    }
  }, [projectId])

  const isOwner = project.role === 'owner'
  const canAddMembers = isOwner || project.role === 'admin'

  async function submitAdd(event) {
    event.preventDefault()
    setFormError('')
    setIsAdding(true)
    try {
      await addMember(projectId, { email: email.trim(), role })
      setEmail('')
      setRole('member')
      await reload()
      await refreshProject()
      showToast('Member added.', 'success')
    } catch (requestError) {
      setFormError(
        getErrorMessage(requestError, 'The member could not be added.'),
      )
    } finally {
      setIsAdding(false)
    }
  }

  async function saveRole(member) {
    try {
      await updateMemberRole(projectId, member.id, {
        role: selectedRoles[member.id] || member.role,
      })
      await reload()
      await refreshProject()
      showToast(`${member.username}’s role was updated.`, 'success')
    } catch (requestError) {
      setFormError(
        getErrorMessage(requestError, 'The member role could not be updated.'),
      )
    }
  }

  async function confirmRemove() {
    if (!pendingMember) {
      return
    }
    setIsRemoving(true)
    try {
      await removeMember(projectId, pendingMember.id)
      const leaving = pendingMember.id === user.id
      setPendingMember(null)
      if (leaving) {
        showToast('You left the project.', 'success')
        navigate('/dashboard')
        return
      }
      await reload()
      await refreshProject()
      showToast(`${pendingMember.username} was removed.`, 'success')
    } catch (requestError) {
      setFormError(
        getErrorMessage(requestError, 'The member could not be removed.'),
      )
      setPendingMember(null)
    } finally {
      setIsRemoving(false)
    }
  }

  function mayRemove(member) {
    if (member.role === 'owner') {
      return false
    }
    if (isOwner) {
      return member.id !== user.id
    }
    if (project.role === 'admin') {
      return member.role === 'member' && member.id !== user.id
    }
    return project.role === 'member' && member.id === user.id
  }

  return (
    <section className="members-page" aria-labelledby="members-heading">
      <div className="members-page-heading">
        <div>
          <h2 id="members-heading">Members</h2>
          <p>People who can access this project.</p>
        </div>
        <span className="muted-count">
          {project.member_count}{' '}
          {project.member_count === 1 ? 'person' : 'people'}
        </span>
      </div>

      {canAddMembers && (
        <form className="add-member-form" onSubmit={submitAdd}>
          <div className="form-field member-email-field">
            <label htmlFor="member-email">Add someone by email</label>
            <input
              id="member-email"
              type="email"
              autoComplete="email"
              placeholder="name@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </div>
          {isOwner && (
            <div className="form-field member-role-field">
              <label htmlFor="member-role">Role</label>
              <select
                id="member-role"
                value={role}
                onChange={(event) => setRole(event.target.value)}
              >
                <option value="member">Member</option>
                <option value="admin">Admin</option>
              </select>
            </div>
          )}
          <button className="primary-button" type="submit" disabled={isAdding}>
            {isAdding ? 'Adding…' : 'Add member'}
          </button>
          {formError && (
            <p className="form-server-error member-form-error" role="alert">
              {formError}
            </p>
          )}
        </form>
      )}

      {loadError ? (
        <ErrorState message={loadError} onRetry={reload} />
      ) : isLoading ? (
        <Skeleton count={3} className="member-list" />
      ) : members.length === 0 ? (
        <EmptyState title="No project members yet">
          Invite teammates by email to collaborate on this project.
        </EmptyState>
      ) : (
        <ul className="member-list">
          {members.map((member) => (
            <li className="member-row" key={member.id}>
              <Avatar name={member.username} />
              <div className="member-identity">
                <strong>{member.username}</strong>
                <span>{member.email}</span>
              </div>
              {isOwner && member.role !== 'owner' ? (
                <div className="member-role-editor">
                  <label
                    className="visually-hidden"
                    htmlFor={`role-${member.id}`}
                  >
                    Role for {member.username}
                  </label>
                  <select
                    id={`role-${member.id}`}
                    value={selectedRoles[member.id] || member.role}
                    onChange={(event) =>
                      setSelectedRoles((roles) => ({
                        ...roles,
                        [member.id]: event.target.value,
                      }))
                    }
                  >
                    <option value="member">Member</option>
                    <option value="admin">Admin</option>
                  </select>
                  {(selectedRoles[member.id] || member.role) !==
                    member.role && (
                    <button
                      className="text-button"
                      type="button"
                      onClick={() => saveRole(member)}
                    >
                      Save
                    </button>
                  )}
                </div>
              ) : (
                <Badge tone={ROLE_TONES[member.role]}>{member.role}</Badge>
              )}
              {mayRemove(member) && (
                <button
                  className="text-button danger-text"
                  type="button"
                  onClick={() => setPendingMember(member)}
                >
                  {member.id === user.id ? 'Leave project' : 'Remove'}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {formError && !canAddMembers && (
        <p className="form-server-error" role="alert">
          {formError}
        </p>
      )}

      {pendingMember && (
        <ConfirmDialog
          title={
            pendingMember.id === user.id ? 'Leave project?' : 'Remove member?'
          }
          message={
            pendingMember.id === user.id
              ? 'You will lose access to this project immediately.'
              : `${pendingMember.username} will lose access to this project immediately.`
          }
          confirmLabel={
            pendingMember.id === user.id ? 'Leave project' : 'Remove member'
          }
          isDestructive
          isLoading={isRemoving}
          onClose={() => setPendingMember(null)}
          onConfirm={confirmRemove}
        />
      )}
    </section>
  )
}
