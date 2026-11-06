import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  MemoryRouter,
  Route,
  Routes,
  useOutletContext,
} from 'react-router-dom'
import { AuthContext } from '../context/AuthContext'
import { ToastProvider } from '../context/ToastContext.jsx'
import * as projectApi from '../features/projects/api'
import ProjectPage from './ProjectPage'

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

const project = {
  id: 'project-id',
  name: 'Team project',
  description: 'Project description',
  owner_id: 'owner-id',
  role: 'owner',
  member_count: 2,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

function ProjectPanel() {
  const { refreshProject } = useOutletContext()
  return (
    <>
      <h2>Member panel</h2>
      <button type="button" onClick={refreshProject}>
        Refresh project
      </button>
    </>
  )
}

function renderProject(role = 'owner', initialEntry = '/projects/project-id') {
  projectApi.getProject.mockResolvedValue({ ...project, role })
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <ToastProvider>
        <AuthContext.Provider
          value={{ user: { id: 'owner-id', username: 'Owner' } }}
        >
          <Routes>
            <Route path="/projects/:projectId" element={<ProjectPage />}>
              <Route path="members" element={<ProjectPanel />} />
            </Route>
          </Routes>
        </AuthContext.Provider>
      </ToastProvider>
    </MemoryRouter>,
  )
}

describe('ProjectPage', () => {
  beforeEach(() => {
    projectApi.getProject.mockReset()
    projectApi.updateProject.mockReset()
    projectApi.deleteProject.mockReset()
  })

  afterEach(() => cleanup())

  it('shows project settings controls only to the owner', async () => {
    renderProject('admin')

    expect(
      await screen.findByRole('heading', { name: 'Team project' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Edit settings' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Delete project' }),
    ).not.toBeInTheDocument()
  })

  it('lets the owner edit the project name and description', async () => {
    const user = userEvent.setup()
    projectApi.updateProject.mockResolvedValue({
      ...project,
      name: 'Renamed project',
    })
    renderProject()

    await screen.findByRole('heading', { name: 'Team project' })
    await user.click(screen.getByRole('button', { name: 'Edit settings' }))
    const name = screen.getByLabelText('Project name')
    await user.clear(name)
    await user.type(name, 'Renamed project')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(projectApi.updateProject).toHaveBeenCalledWith('project-id', {
      name: 'Renamed project',
      description: 'Project description',
    })
    expect(
      await screen.findByRole('heading', { name: 'Renamed project' }),
    ).toBeInTheDocument()
  })

  it('requires confirmation before deleting a project', async () => {
    const user = userEvent.setup()
    renderProject()

    await screen.findByRole('heading', { name: 'Team project' })
    await user.click(screen.getByRole('button', { name: 'Delete project' }))
    expect(
      screen.getByRole('dialog', { name: 'Delete project?' }),
    ).toBeInTheDocument()
    expect(projectApi.deleteProject).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('keeps the project page mounted while refreshing project data', async () => {
    const user = userEvent.setup()
    let resolveRefresh
    projectApi.getProject
      .mockResolvedValueOnce({ ...project })
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveRefresh = resolve
        }),
      )
    renderProject('owner', '/projects/project-id/members')

    expect(await screen.findByRole('heading', { name: 'Member panel' }))
      .toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Refresh project' }))

    expect(screen.getByRole('heading', { name: 'Member panel' }))
      .toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Team project' }),
    ).toBeInTheDocument()

    resolveRefresh({ ...project, name: 'Updated project' })
    expect(
      await screen.findByRole('heading', { name: 'Updated project' }),
    ).toBeInTheDocument()
  })
})
