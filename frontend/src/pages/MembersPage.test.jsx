import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { AuthContext } from '../context/AuthContext'
import { ToastProvider } from '../context/ToastContext.jsx'
import * as projectApi from '../features/projects/api'
import MembersPage from './MembersPage'

vi.mock('../features/projects/api', () => ({
  listProjects: vi.fn(),
  createProject: vi.fn(),
  getProject: vi.fn(),
  updateProject: vi.fn(),
  deleteProject: vi.fn(),
  listMembers: vi.fn(),
  addMember: vi.fn(),
  updateMemberRole: vi.fn(),
  removeMember: vi.fn(),
  getErrorMessage: vi.fn(
    (error, fallback) => error?.response?.data?.detail || fallback,
  ),
}))

const members = [
  {
    id: 'owner-id',
    username: 'Owner One',
    email: 'owner@example.com',
    role: 'owner',
    joined_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'admin-id',
    username: 'Admin Two',
    email: 'admin@example.com',
    role: 'admin',
    joined_at: '2026-01-02T00:00:00Z',
  },
  {
    id: 'member-id',
    username: 'Member Three',
    email: 'member@example.com',
    role: 'member',
    joined_at: '2026-01-03T00:00:00Z',
  },
]

const defaultProject = {
  id: 'project-id',
  name: 'Team project',
  role: 'owner',
  member_count: 3,
}

function ProjectLayout({ project = defaultProject, refreshProject = vi.fn() }) {
  return <Outlet context={{ project, refreshProject }} />
}

function renderMembers({ role = 'owner', userId = 'owner-id' } = {}) {
  const project = { ...defaultProject, role }
  const user = {
    id: userId,
    username: 'Current user',
    email: 'current@example.com',
  }
  return render(
    <MemoryRouter initialEntries={['/projects/project-id/members']}>
      <ToastProvider>
        <AuthContext.Provider value={{ user }}>
          <Routes>
            <Route
              path="/projects/:projectId"
              element={<ProjectLayout project={project} />}
            >
              <Route path="members" element={<MembersPage />} />
            </Route>
            <Route path="/dashboard" element={<h1>Dashboard</h1>} />
          </Routes>
        </AuthContext.Provider>
      </ToastProvider>
    </MemoryRouter>,
  )
}

describe('MembersPage', () => {
  beforeEach(() => {
    projectApi.listMembers.mockReset()
    projectApi.listMembers.mockResolvedValue(members)
    projectApi.addMember.mockReset()
    projectApi.updateMemberRole.mockReset()
    projectApi.removeMember.mockReset()
  })

  afterEach(() => cleanup())

  it('lets owners add admins and change/remove non-owner roles', async () => {
    renderMembers()

    expect(await screen.findByText('Owner One')).toBeInTheDocument()
    expect(screen.getByLabelText('Role')).toBeInTheDocument()
    expect(screen.getByLabelText('Role for Admin Two')).toBeInTheDocument()
    expect(screen.getByLabelText('Role for Member Three')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Remove' })).toHaveLength(2)
    expect(
      screen.queryByRole('button', { name: 'Leave project' }),
    ).not.toBeInTheDocument()
  })

  it('lets admins add members and remove members, but hides role changes', async () => {
    renderMembers({ role: 'admin', userId: 'admin-id' })

    expect(await screen.findByText('Owner One')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Add member' }),
    ).toBeInTheDocument()
    expect(screen.queryByLabelText('Role')).not.toBeInTheDocument()
    expect(
      screen.queryByLabelText('Role for Member Three'),
    ).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Remove' })).toHaveLength(1)
    expect(
      screen.queryByRole('button', { name: 'Leave project' }),
    ).not.toBeInTheDocument()
  })

  it('only lets a member leave their own project', async () => {
    renderMembers({ role: 'member', userId: 'member-id' })

    expect(await screen.findByText('Owner One')).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Add member' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Remove' }),
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Leave project' }),
    ).toBeInTheDocument()
  })

  it('shows clear feedback when the invited email is not registered', async () => {
    const user = userEvent.setup()
    projectApi.addMember.mockRejectedValue({
      response: { data: { detail: 'No registered user with that email.' } },
    })
    renderMembers()

    await screen.findByText('Owner One')
    await user.type(
      screen.getByLabelText('Add someone by email'),
      'unknown@example.com',
    )
    await user.click(screen.getByRole('button', { name: 'Add member' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'No registered user with that email.',
    )
  })

  it('shows duplicate-member feedback from the API', async () => {
    const user = userEvent.setup()
    projectApi.addMember.mockRejectedValue({
      response: { data: { detail: 'This user is already a project member.' } },
    })
    renderMembers()

    await screen.findByText('Owner One')
    await user.type(
      screen.getByLabelText('Add someone by email'),
      'member@example.com',
    )
    await user.click(screen.getByRole('button', { name: 'Add member' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This user is already a project member.',
    )
  })

  it('confirms before removing a member and closes on cancel', async () => {
    const user = userEvent.setup()
    renderMembers()

    await screen.findByText('Owner One')
    await user.click(screen.getAllByRole('button', { name: 'Remove' })[0])
    expect(
      screen.getByRole('dialog', { name: 'Remove member?' }),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(projectApi.removeMember).not.toHaveBeenCalled()
  })
})
