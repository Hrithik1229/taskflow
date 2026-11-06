import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { AuthContext } from '../context/AuthContext'
import { ToastProvider } from '../context/ToastContext.jsx'
import * as projectApi from '../features/projects/api'
import * as taskApi from '../features/tasks/api'
import DashboardPage from './DashboardPage'

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

vi.mock('../features/tasks/api', () => ({
  getDashboardSummary: vi.fn(),
  getDashboardBreakdown: vi.fn(),
  getTaskErrorMessage: vi.fn((_error, fallback) => fallback),
}))

const userProfile = {
  id: 'user-id',
  username: 'Taylor',
  email: 'taylor@example.com',
}

const project = {
  id: 'project-id',
  name: 'Launch plan',
  description: 'Coordinate the release',
  role: 'owner',
  member_count: 3,
}

function renderDashboard() {
  return render(
    <MemoryRouter>
      <ToastProvider>
        <AuthContext.Provider value={{ user: userProfile }}>
          <DashboardPage />
        </AuthContext.Provider>
      </ToastProvider>
    </MemoryRouter>,
  )
}

describe('DashboardPage', () => {
  beforeEach(() => {
    projectApi.listProjects.mockReset()
    projectApi.createProject.mockReset()
    projectApi.listProjects.mockResolvedValue([])
    taskApi.getDashboardSummary.mockResolvedValue({
      total_tasks: 0,
      assigned_to_me: 0,
      overdue: 0,
      completed: 0,
    })
    taskApi.getDashboardBreakdown.mockResolvedValue({
      metric: 'total',
      total_count: 0,
      projects: [],
    })
  })

  afterEach(() => cleanup())

  it('shows loading skeletons while projects load', () => {
    projectApi.listProjects.mockReturnValue(new Promise(() => {}))
    const { container } = renderDashboard()

    expect(
      container.querySelector('.project-grid.skeleton-list'),
    ).toBeInTheDocument()
  })

  it('shows an empty state and call to action', async () => {
    const user = userEvent.setup()
    renderDashboard()

    expect(
      await screen.findByText('Your projects will show up here'),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Create project' }))
    expect(
      screen.getByRole('dialog', { name: 'Create a project' }),
    ).toBeInTheDocument()
  })

  it('shows an error and retries the project request', async () => {
    const user = userEvent.setup()
    projectApi.listProjects
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce([project])
    renderDashboard()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Projects could not be loaded.',
    )
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(
      await screen.findByRole('link', { name: /Launch plan/ }),
    ).toBeInTheDocument()
  })

  it('renders real project summary information', async () => {
    projectApi.listProjects.mockResolvedValue([project])
    renderDashboard()

    expect(
      await screen.findByRole('link', { name: /Launch plan/ }),
    ).toHaveAttribute('href', '/projects/project-id')
    expect(screen.getByText('Coordinate the release')).toBeInTheDocument()
    expect(screen.getByText('owner')).toBeInTheDocument()
    expect(screen.getByText('3 members')).toBeInTheDocument()
  })

  it('renders task metrics from the dashboard summary endpoint', async () => {
    taskApi.getDashboardSummary.mockResolvedValue({
      total_tasks: 12,
      assigned_to_me: 4,
      overdue: 2,
      completed: 5,
    })
    renderDashboard()

    expect(await screen.findByText('12')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('opens an accessible project breakdown and restores focus on Escape', async () => {
    const user = userEvent.setup()
    taskApi.getDashboardSummary.mockResolvedValue({
      total_tasks: 12,
      assigned_to_me: 4,
      overdue: 2,
      completed: 5,
    })
    taskApi.getDashboardBreakdown.mockResolvedValue({
      metric: 'overdue',
      total_count: 1,
      projects: [
        {
          project_id: 'project-id',
          project_name: 'Launch plan',
          count: 1,
          has_more: false,
          tasks: [
            {
              id: 'overdue-task',
              title: 'Fix release blocker',
              status: 'in_progress',
              priority: 'urgent',
              due_at: '2026-01-01T00:00:00Z',
              assignee: { id: 'user-id', username: 'Taylor' },
              completed_by: null,
            },
          ],
        },
      ],
    })
    renderDashboard()

    const card = await screen.findByRole('button', {
      name: /Overdue: 2/,
    })
    await user.click(card)

    expect(card).toHaveAttribute('aria-expanded', 'true')
    expect(card).toHaveAttribute('aria-controls', 'dashboard-breakdown-panel')
    expect(
      await screen.findByRole('heading', { name: 'Overdue by project' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Launch plan' }),
    ).toHaveAttribute('href', '/projects/project-id/board')
    expect(
      screen.getByRole('link', { name: 'Fix release blocker' }),
    ).toHaveAttribute(
      'href',
      '/projects/project-id/board?task=overdue-task',
    )
    await user.keyboard('{Escape}')
    expect(card).toHaveAttribute('aria-expanded', 'false')
    expect(document.activeElement).toBe(card)
  })

  it('shows the credited completer in a completed-task breakdown', async () => {
    const user = userEvent.setup()
    taskApi.getDashboardBreakdown.mockResolvedValue({
      metric: 'completed',
      total_count: 1,
      projects: [
        {
          project_id: 'project-id',
          project_name: 'Launch plan',
          count: 1,
          has_more: false,
          tasks: [
            {
              id: 'completed-task',
              title: 'Review approved',
              status: 'completed',
              priority: 'high',
              due_at: null,
              assignee: null,
              completed_by: { id: 'user-id', username: 'Taylor' },
              completed_by_removed: false,
            },
          ],
        },
      ],
    })
    renderDashboard()

    await user.click(
      await screen.findByRole('button', { name: /Completed: 0/ }),
    )

    expect(await screen.findByText('Completed by Taylor')).toBeInTheDocument()
  })

  it('shows empty and retryable error states for breakdown requests', async () => {
    const user = userEvent.setup()
    taskApi.getDashboardBreakdown
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({
        metric: 'completed',
        total_count: 0,
        projects: [],
      })
    renderDashboard()

    await user.click(
      await screen.findByRole('button', { name: /Completed: 0/ }),
    )
    expect(
      await screen.findByText('Task breakdown could not be loaded.'),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(
      await screen.findByText('No tasks in this category'),
    ).toBeInTheDocument()
    expect(taskApi.getDashboardBreakdown).toHaveBeenCalledTimes(2)
  })

  it('creates a project and reloads the project list', async () => {
    const user = userEvent.setup()
    projectApi.listProjects
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([project])
    projectApi.createProject.mockResolvedValue(project)
    renderDashboard()

    await screen.findByText('Your projects will show up here')
    await user.click(screen.getByRole('button', { name: 'Create project' }))
    await user.type(screen.getByLabelText('Project name'), 'Launch plan')
    await user.type(
      screen.getByLabelText('Description'),
      'Coordinate the release',
    )
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Create project',
      }),
    )

    expect(projectApi.createProject).toHaveBeenCalledWith({
      name: 'Launch plan',
      description: 'Coordinate the release',
    })
    expect(
      await screen.findByRole('link', { name: /Launch plan/ }),
    ).toBeInTheDocument()
  })

  it('shows a server error when project creation fails', async () => {
    const user = userEvent.setup()
    projectApi.createProject.mockRejectedValue({
      response: { data: { detail: 'Project could not be created.' } },
    })
    renderDashboard()

    await screen.findByText('Your projects will show up here')
    await user.click(screen.getByRole('button', { name: 'Create project' }))
    await user.type(screen.getByLabelText('Project name'), 'Launch plan')
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: 'Create project',
      }),
    )

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Project could not be created.',
    )
  })
})
