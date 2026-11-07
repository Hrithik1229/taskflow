import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { AuthContext } from '../context/AuthContext'
import * as taskApi from '../features/tasks/api'
import { useTasks } from '../features/tasks/hooks'
import BoardPage from './BoardPage'

vi.mock('../features/tasks/hooks', () => ({
  useTasks: vi.fn(),
}))

vi.mock('../features/tasks/api', () => ({
  createTask: vi.fn(),
  deleteTask: vi.fn(),
  getTask: vi.fn(),
  getTaskErrorMessage: vi.fn((error, fallback) => error?.message || fallback),
  listProjectMembers: vi.fn(),
  listTasks: vi.fn(),
  updateTask: vi.fn(),
  listComments: vi.fn().mockResolvedValue([]),
  createComment: vi.fn(),
  listProjectActivity: vi.fn().mockResolvedValue({ items: [], total: 0 }),
}))

vi.mock('../context/ToastContext.js', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}))

const project = {
  id: 'project-id',
  name: 'Board project',
  role: 'owner',
}

const task = {
  id: 'task-id',
  project_id: 'project-id',
  title: 'Review launch checklist',
  description: 'Check the release details',
  status: 'todo',
  priority: 'high',
  assigned_to: null,
  assignee: null,
  created_by: 'owner-id',
  creator: { id: 'owner-id', username: 'Owner' },
  due_at: null,
  reviewer_id: null,
  reviewer: null,
  review_requested_by: null,
  status_changed_by: null,
  status_changed_at: null,
  completed_by: null,
  completed_at: null,
  position: 0,
  version: 1,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

function renderBoard({
  initialEntry = '/projects/project-id/board',
  currentProject = project,
  currentUser = { id: 'owner-id', username: 'Owner' },
} = {}) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <AuthContext.Provider value={{ user: currentUser }}>
        <Routes>
          <Route
            path="/projects/:projectId"
            element={<Outlet context={{ project: currentProject }} />}
          >
            <Route path="board" element={<BoardPage />} />
          </Route>
        </Routes>
      </AuthContext.Provider>
    </MemoryRouter>,
  )
}

describe('BoardPage', () => {
  beforeEach(() => {
    useTasks.mockReturnValue({
      tasks: [task],
      isLoading: false,
      error: '',
      reload: vi.fn().mockResolvedValue(undefined),
      move: vi.fn().mockResolvedValue(undefined),
    })
    taskApi.listProjectMembers.mockResolvedValue([])
    taskApi.getTask.mockResolvedValue(task)
    taskApi.createTask.mockResolvedValue(task)
  })

  afterEach(() => cleanup())

  it('renders the four task columns and real task cards', async () => {
    renderBoard()

    expect(
      await screen.findByText('Review launch checklist'),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('region', { name: 'To do tasks' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('region', { name: 'In progress tasks' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('region', { name: 'Review tasks' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('region', { name: 'Completed tasks' }),
    ).toBeInTheDocument()
  })

  it('creates a task using the real task API', async () => {
    const user = userEvent.setup()
    renderBoard()

    await user.click(await screen.findByRole('button', { name: 'Create task' }))
    await user.type(screen.getByLabelText('Title'), 'Prepare launch')
    await user.click(screen.getAllByRole('button', { name: 'Create task' })[1])

    await waitFor(() => {
      expect(taskApi.createTask).toHaveBeenCalledWith(
        'project-id',
        expect.objectContaining({
          title: 'Prepare launch',
          status: 'todo',
          priority: 'medium',
        }),
      )
    })
  })

  it('opens a task from the board query parameter', async () => {
    useTasks.mockReturnValue({
      tasks: [],
      isLoading: false,
      error: '',
      reload: vi.fn().mockResolvedValue(undefined),
      move: vi.fn().mockResolvedValue(undefined),
    })
    taskApi.getTask.mockResolvedValue({
      ...task,
      status_changed_by: { id: 'owner-id', username: 'Owner' },
      status_changed_at: '2026-01-02T00:00:00Z',
    })
    renderBoard({
      initialEntry: '/projects/project-id/board?task=task-id',
    })

    expect(
      await screen.findByRole('dialog', { name: 'Task details' }),
    ).toBeInTheDocument()
    expect(taskApi.getTask).toHaveBeenCalledWith('task-id')
  })

  it('shows status attribution and the reviewer selector to permitted users', async () => {
    const user = userEvent.setup()
    const reviewTask = {
      ...task,
      status: 'review',
      reviewer_id: 'reviewer-id',
      reviewer: { id: 'reviewer-id', username: 'Reviewer' },
      review_requested_by: { id: 'submitter-id', username: 'Submitter' },
      status_changed_by: { id: 'submitter-id', username: 'Submitter' },
      status_changed_at: '2026-01-02T00:00:00Z',
    }
    useTasks.mockReturnValue({
      tasks: [reviewTask],
      isLoading: false,
      error: '',
      reload: vi.fn().mockResolvedValue(undefined),
      move: vi.fn().mockResolvedValue(undefined),
    })
    taskApi.listProjectMembers.mockResolvedValue([
      { id: 'submitter-id', username: 'Submitter' },
      { id: 'reviewer-id', username: 'Reviewer' },
      { id: 'replacement-id', username: 'Replacement' },
    ])
    renderBoard()

    expect(
      await screen.findByText('Reviewer: Reviewer · from Submitter'),
    ).toBeInTheDocument()
    await user.click(
      screen.getByRole('button', { name: reviewTask.title }),
    )
    expect(screen.getByText('Status history')).toBeInTheDocument()
    const reviewerSelect = screen.getByLabelText('Reviewer')
    expect(reviewerSelect).toBeInTheDocument()
    expect(
      within(reviewerSelect).getByRole('option', { name: 'Replacement' }),
    ).toBeInTheDocument()
    expect(
      within(reviewerSelect).queryByRole('option', { name: 'Submitter' }),
    ).not.toBeInTheDocument()
  })

  it('shows former completers and hides missing legacy movement attribution', async () => {
    const formerCompletion = {
      ...task,
      id: 'former-completion',
      title: 'Completed by a removed member',
      status: 'completed',
      completed_by: null,
      completed_at: '2026-01-02T00:00:00Z',
      completed_by_removed: true,
    }
    const legacyTask = {
      ...task,
      id: 'legacy-task',
      title: 'Legacy in-progress task',
      status: 'in_progress',
      status_changed_by: null,
      status_changed_at: null,
    }
    useTasks.mockReturnValue({
      tasks: [formerCompletion, legacyTask],
      isLoading: false,
      error: '',
      reload: vi.fn().mockResolvedValue(undefined),
      move: vi.fn().mockResolvedValue(undefined),
    })
    renderBoard()

    expect(
      await screen.findByText('Completed by Former member'),
    ).toBeInTheDocument()
    const legacyCard = screen
      .getByRole('button', { name: legacyTask.title })
      .closest('article')
    expect(
      within(legacyCard).queryByText(/Moved by/),
    ).not.toBeInTheDocument()
  })

  it('disables Review drag handles for members who are not the reviewer', async () => {
    const reviewTask = {
      ...task,
      status: 'review',
      reviewer_id: 'reviewer-id',
      reviewer: { id: 'reviewer-id', username: 'Reviewer' },
      review_requested_by: { id: 'submitter-id', username: 'Submitter' },
    }
    useTasks.mockReturnValue({
      tasks: [reviewTask],
      isLoading: false,
      error: '',
      reload: vi.fn().mockResolvedValue(undefined),
      move: vi.fn().mockResolvedValue(undefined),
    })
    renderBoard({
      currentProject: { ...project, role: 'member' },
      currentUser: { id: 'other-id', username: 'Other' },
    })

    const dragHandle = await screen.findByRole('button', {
      name: `Move task ${reviewTask.title}`,
    })
    expect(dragHandle).toBeDisabled()
    expect(dragHandle.getAttribute('aria-describedby')).toContain(
      `drag-disabled-${reviewTask.id}`,
    )
    expect(
      screen.getByText(
        'Only the reviewer, project owner, or admin can move a task out of Review.',
      ),
    ).toBeInTheDocument()
  })
})
