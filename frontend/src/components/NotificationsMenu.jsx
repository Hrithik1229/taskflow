import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from '../features/tasks/api'
import {
  connectRealtimeSocket,
} from '../realtime/socket'
import Avatar from './Avatar'

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

function notificationText(notification) {
  const actor = notification.actor?.username || 'Someone'
  const title = notification.payload?.title || notification.payload?.task_title || 'a task'

  switch (notification.type) {
    case 'task_assigned':
      return `${actor} assigned you to “${title}”`
    case 'task_updated':
      return `${actor} updated “${title}”`
    case 'comment_added':
      return `${actor} commented on “${title}”`
    case 'review_requested':
      return `${actor} requested your review on “${title}”`
    case 'changes_requested':
      return `${actor} requested changes on “${title}”`
    case 'review_completed':
      return `${actor} completed review on “${title}”`
    case 'member_added':
      return `${actor} added you to a project`
    case 'member_removed':
      return `${actor} removed you from a project`
    default:
      return `${actor} sent an update`
  }
}

export default function NotificationsMenu() {
  const { token } = useAuth()
  const navigate = useNavigate()
  const [isOpen, setIsOpen] = useState(false)
  const [notifications, setNotifications] = useState([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const menuRef = useRef(null)
  const buttonRef = useRef(null)

  const fetchNotifications = async () => {
    if (!token) return
    setIsLoading(true)
    setError('')
    try {
      const data = await listNotifications({ limit: 20 })
      setNotifications(data.items || [])
      setUnreadCount(data.unread_count || 0)
    } catch {
      setError('Could not load notifications.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    let active = true
    if (!token) return undefined
    listNotifications({ limit: 20 })
      .then((data) => {
        if (active) {
          setNotifications(data.items || [])
          setUnreadCount(data.unread_count || 0)
        }
      })
      .catch(() => {
        if (active) setError('Could not load notifications.')
      })
    return () => {
      active = false
    }
  }, [token])

  useEffect(() => {
    if (!token) return undefined
    const socket = connectRealtimeSocket(token)

    const handleNotification = (payload) => {
      const notif = payload?.notification
      if (!notif) return

      const formatted = {
        ...notif,
        actor: payload.actor,
        project_id: payload.project_id,
      }
      setNotifications((prev) => [formatted, ...prev])
      setUnreadCount((prev) => prev + 1)
    }

    const handleConnect = () => {
      fetchNotifications()
    }

    socket.on('notification_created', handleNotification)
    socket.on('connect', handleConnect)

    return () => {
      socket.off('notification_created', handleNotification)
      socket.off('connect', handleConnect)
    }
  }, [token]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!isOpen) return undefined
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }
    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        setIsOpen(false)
        buttonRef.current?.focus()
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen])

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead()
      setNotifications((prev) =>
        prev.map((n) => ({ ...n, read_at: n.read_at || new Date().toISOString() })),
      )
      setUnreadCount(0)
    } catch {
      // ignore
    }
  }

  const handleNotificationClick = async (notification) => {
    if (!notification.read_at) {
      try {
        await markNotificationRead(notification.id)
        setNotifications((prev) =>
          prev.map((n) =>
            n.id === notification.id
              ? { ...n, read_at: new Date().toISOString() }
              : n,
          ),
        )
        setUnreadCount((prev) => Math.max(0, prev - 1))
      } catch {
        // ignore
      }
    }

    setIsOpen(false)
    const taskId = notification.payload?.task_id
    const projectId = notification.project_id || notification.payload?.project_id

    if (projectId && taskId) {
      navigate(`/projects/${projectId}/board?task=${taskId}`)
    } else if (projectId) {
      navigate(`/projects/${projectId}/board`)
    }
  }

  return (
    <div className="notifications-menu" ref={menuRef}>
      <button
        ref={buttonRef}
        type="button"
        className="icon-button notifications-bell-button"
        aria-label={`Notifications${unreadCount > 0 ? `, ${unreadCount} unread` : ''}`}
        aria-expanded={isOpen}
        aria-haspopup="true"
        onClick={() => setIsOpen((prev) => !prev)}
      >
        <span aria-hidden="true">🔔</span>
        {unreadCount > 0 && (
          <span className="notifications-badge" aria-hidden="true">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div
          className="notifications-dropdown"
          role="region"
          aria-label="Notifications list"
        >
          <header className="notifications-header">
            <h3>Notifications</h3>
            {unreadCount > 0 && (
              <button
                type="button"
                className="text-button mark-all-read-btn"
                onClick={handleMarkAllRead}
              >
                Mark all read
              </button>
            )}
          </header>

          <div className="notifications-list" role="feed">
            {isLoading && notifications.length === 0 ? (
              <p className="notifications-empty">Loading notifications…</p>
            ) : error ? (
              <div className="notifications-error" role="alert">
                <p>{error}</p>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={fetchNotifications}
                >
                  Retry
                </button>
              </div>
            ) : notifications.length === 0 ? (
              <p className="notifications-empty">No notifications yet</p>
            ) : (
              notifications.map((notification) => {
                const isUnread = !notification.read_at
                return (
                  <button
                    key={notification.id}
                    type="button"
                    className={`notification-item${isUnread ? ' notification-item--unread' : ''}`}
                    onClick={() => handleNotificationClick(notification)}
                  >
                    <div className="notification-item-avatar">
                      <Avatar
                        name={notification.actor?.username || 'User'}
                        size="small"
                      />
                    </div>
                    <div className="notification-item-body">
                      <p className="notification-item-text">
                        {notificationText(notification)}
                      </p>
                      <time
                        className="notification-item-time"
                        dateTime={notification.created_at}
                        title={new Date(notification.created_at).toLocaleString()}
                      >
                        {relativeTime(notification.created_at)}
                      </time>
                    </div>
                    {isUnread && (
                      <span
                        className="notification-item-unread-dot"
                        aria-label="Unread"
                      />
                    )}
                  </button>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}
