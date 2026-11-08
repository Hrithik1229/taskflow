import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import * as taskApi from '../features/tasks/api'
import { AuthContext } from '../context/AuthContext'
import NotificationsMenu from './NotificationsMenu'

const { socket, socketHandlers } = vi.hoisted(() => {
  const handlers = new Map()
  return {
    socketHandlers: handlers,
    socket: {
      on: vi.fn((event, handler) => handlers.set(event, handler)),
      off: vi.fn((event) => handlers.delete(event)),
    },
  }
})

vi.mock('../features/tasks/api', () => ({
  listNotifications: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  markNotificationRead: vi.fn(),
}))

vi.mock('../realtime/socket', () => ({
  connectRealtimeSocket: vi.fn(() => socket),
}))

function LocationDisplay() {
  const location = useLocation()
  return (
    <output aria-label="current location">
      {location.pathname + location.search}
    </output>
  )
}

function renderMenu() {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <AuthContext.Provider value={{ token: 'access-token' }}>
        <Routes>
          <Route
            path="*"
            element={
              <>
                <NotificationsMenu />
                <LocationDisplay />
              </>
            }
          />
        </Routes>
      </AuthContext.Provider>
    </MemoryRouter>,
  )
}

const notification = {
  id: 'notification-1',
  type: 'task_assigned',
  read_at: null,
  project_id: 'project-1',
  actor: { username: 'Taylor' },
  payload: { title: 'Write tests', task_id: 'task-1' },
}

describe('NotificationsMenu', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    socketHandlers.clear()
    taskApi.listNotifications.mockResolvedValue({
      items: [notification],
      unread_count: 1,
    })
    taskApi.markNotificationRead.mockResolvedValue({})
    taskApi.markAllNotificationsRead.mockResolvedValue({})
  })

  afterEach(() => cleanup())

  it('marks a notification as read and navigates to its task', async () => {
    const user = userEvent.setup()
    renderMenu()

    await user.click(
      await screen.findByRole('button', { name: 'Notifications, 1 unread' }),
    )
    await user.click(
      screen.getByRole('button', { name: /Taylor assigned you to/ }),
    )

    expect(taskApi.markNotificationRead).toHaveBeenCalledWith(notification.id)
    await waitFor(() => {
      expect(screen.getByLabelText('current location')).toHaveTextContent(
        '/projects/project-1/board?task=task-1',
      )
    })
  })

  it('updates the unread count when a realtime notification arrives', async () => {
    renderMenu()
    await screen.findByRole('button', { name: 'Notifications, 1 unread' })

    act(() => {
      socketHandlers.get('notification_created')({
        project_id: 'project-2',
        actor: { username: 'Morgan' },
        notification: {
          ...notification,
          id: 'notification-2',
          payload: { title: 'Review task' },
        },
      })
    })

    expect(
      screen.getByRole('button', { name: 'Notifications, 2 unread' }),
    ).toBeInTheDocument()
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: 'Notifications, 2 unread' }))
    expect(
      await screen.findByRole('button', { name: /Morgan assigned you to/ }),
    ).toBeInTheDocument()
  })

  it('marks all loaded notifications as read', async () => {
    const user = userEvent.setup()
    renderMenu()
    await user.click(
      await screen.findByRole('button', { name: 'Notifications, 1 unread' }),
    )
    await user.click(screen.getByRole('button', { name: 'Mark all read' }))

    expect(taskApi.markAllNotificationsRead).toHaveBeenCalledOnce()
    expect(
      screen.getByRole('button', { name: 'Notifications' }),
    ).toBeInTheDocument()
  })
})
