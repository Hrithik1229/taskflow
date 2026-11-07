import { useEffect, useState } from 'react'
import { listProjectActivity } from './api'

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

function formatAction(action, details) {
  switch (action) {
    case 'task.created':
      return 'created this task'
    case 'task.updated': {
      const fields = Object.keys(details || {}).filter((k) => k !== 'description')
      return fields.length ? `updated ${fields.join(', ')}` : 'updated this task'
    }
    case 'task.moved': {
      const toStatus = details?.to_status ? details.to_status.replace('_', ' ') : 'new column'
      return `moved this task to ${toStatus}`
    }
    case 'comment.created':
      return 'commented on this task'
    case 'task.unassigned':
      return 'unassigned this task'
    case 'task.reviewer_removed':
      return 'reviewer was removed'
    case 'task.completion_credit_removed':
      return 'completion credit adjusted'
    default:
      return action.replace('.', ' ')
  }
}

export default function TaskActivityContext({ taskId, projectId }) {
  const [activities, setActivities] = useState([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let active = true
    if (!projectId || !taskId) return undefined

    listProjectActivity(projectId, { limit: 100 })
      .then((data) => {
        if (!active) return
        const matching = (data.items || []).filter(
          (item) => String(item.entity_id) === String(taskId),
        )
        setActivities(matching)
      })
      .catch(() => {
        // non-blocking
      })
      .finally(() => {
        if (active) setIsLoading(false)
      })

    return () => {
      active = false
    }
  }, [projectId, taskId])

  if (isLoading || activities.length === 0) return null

  return (
    <section className="task-activity-context" aria-labelledby="task-activity-heading">
      <h3 id="task-activity-heading">Task Activity</h3>
      <ul className="task-activity-list">
        {activities.map((item) => (
          <li key={item.id} className="task-activity-item">
            <span className="task-activity-dot" aria-hidden="true" />
            <span className="task-activity-text">
              <strong>{item.actor?.username || 'User'}</strong> {formatAction(item.action, item.details)}
            </span>
            <time
              dateTime={item.created_at}
              title={new Date(item.created_at).toLocaleString()}
              className="task-activity-time"
            >
              {relativeTime(item.created_at)}
            </time>
          </li>
        ))}
      </ul>
    </section>
  )
}

