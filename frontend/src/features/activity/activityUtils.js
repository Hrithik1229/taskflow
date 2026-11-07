export function relativeTime(value) {
  if (!value) return ''
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

export function formatActivityText(activity) {
  const actor = activity.actor?.username || 'Someone'
  const details = activity.details || {}
  const rawTitle = details.title || details.task_title
  const taskTitle = rawTitle ? `“${rawTitle}”` : 'a task'

  switch (activity.action) {
    case 'project.created':
      return `${actor} created the project`
    case 'project.updated':
      return `${actor} updated project settings`
    case 'member.added': {
      const target = details.member_username || 'a member'
      const role = details.role || 'member'
      return `${actor} added ${target} as ${role}`
    }
    case 'member.role_changed': {
      const target = details.member_username || 'a member'
      const role = details.new_role || 'member'
      return `${actor} changed ${target}’s role to ${role}`
    }
    case 'member.removed': {
      const target = details.member_username || 'a member'
      return `${actor} removed ${target} from the project`
    }
    case 'task.created':
      return `${actor} created ${taskTitle}`
    case 'task.updated': {
      const fields = Object.keys(details).filter(
        (k) => !['title', 'task_title', 'description'].includes(k),
      )
      const fieldDesc = fields.length ? fields.join(', ') : 'details'
      return `${actor} updated ${fieldDesc} on ${taskTitle}`
    }
    case 'task.moved': {
      const toStatus = details.to_status
        ? details.to_status.replace('_', ' ')
        : 'new status'
      return `${actor} moved ${taskTitle} to ${toStatus}`
    }
    case 'task.deleted':
      return `${actor} deleted ${taskTitle}`
    case 'comment.created':
      return `${actor} commented on ${taskTitle}`
    case 'task.unassigned':
      return `${actor} unassigned ${taskTitle}`
    case 'task.reviewer_removed':
      return `${actor} removed reviewer from ${taskTitle}`
    case 'task.completion_credit_removed':
      return `${actor} adjusted completion credit on ${taskTitle}`
    default:
      return `${actor} performed ${activity.action.replace('.', ' ')}`
  }
}
