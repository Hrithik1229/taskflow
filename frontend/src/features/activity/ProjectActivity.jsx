import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Avatar from '../../components/Avatar'
import EmptyState from '../../components/EmptyState'
import ErrorState from '../../components/ErrorState'
import Skeleton from '../../components/Skeleton'
import { listProjectActivity } from '../tasks/api'
import { formatActivityText, relativeTime } from './activityUtils'

const PAGE_SIZE = 20

export default function ProjectActivity({ projectId }) {
  const [activities, setActivities] = useState([])
  const [total, setTotal] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [error, setError] = useState('')

  const loadInitial = useCallback(async () => {
    setIsLoading(true)
    setError('')
    try {
      const data = await listProjectActivity(projectId, {
        limit: PAGE_SIZE,
        offset: 0,
      })
      setActivities(data.items || [])
      setTotal(data.total || 0)
    } catch {
      setError('Unable to load project activity.')
    } finally {
      setIsLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    let active = true
    listProjectActivity(projectId, {
      limit: PAGE_SIZE,
      offset: 0,
    })
      .then((data) => {
        if (active) {
          setActivities(data.items || [])
          setTotal(data.total || 0)
        }
      })
      .catch(() => {
        if (active) setError('Unable to load project activity.')
      })
      .finally(() => {
        if (active) setIsLoading(false)
      })

    return () => {
      active = false
    }
  }, [projectId])

  async function handleLoadMore() {
    setIsLoadingMore(true)
    try {
      const data = await listProjectActivity(projectId, {
        limit: PAGE_SIZE,
        offset: activities.length,
      })
      setActivities((prev) => [...prev, ...(data.items || [])])
      setTotal(data.total || 0)
    } catch {
      setError('Unable to load more activity.')
    } finally {
      setIsLoadingMore(false)
    }
  }

  if (isLoading) {
    return (
      <div className="activity-panel" aria-busy="true">
        <Skeleton count={4} />
      </div>
    )
  }

  if (error && activities.length === 0) {
    return <ErrorState message={error} onRetry={loadInitial} />
  }

  if (activities.length === 0) {
    return (
      <div className="activity-panel">
        <EmptyState title="No activity recorded yet">
          Actions taken on tasks, members, and settings in this project will appear here.
        </EmptyState>
      </div>
    )
  }

  return (
    <div className="activity-panel" aria-labelledby="activity-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">AUDIT & COLLABORATION</p>
          <h2 id="activity-heading">Project Activity</h2>
        </div>
        <span className="muted-count">
          Showing {activities.length} of {total} {total === 1 ? 'event' : 'events'}
        </span>
      </div>

      <ul className="activity-feed-list" aria-label="Activity feed">
        {activities.map((item) => {
          const hasTaskLink =
            item.entity_type === 'task' && item.action !== 'task.deleted'
          return (
            <li key={item.id} className="activity-feed-item">
              <Avatar name={item.actor?.username || 'User'} size="small" />
              <div className="activity-feed-content">
                <p className="activity-feed-text">
                  {formatActivityText(item)}
                </p>
                <div className="activity-feed-meta">
                  <time
                    dateTime={item.created_at}
                    title={new Date(item.created_at).toLocaleString()}
                    className="activity-feed-time"
                  >
                    {relativeTime(item.created_at)}
                  </time>
                  {hasTaskLink && (
                    <>
                      <span aria-hidden="true">·</span>
                      <Link
                        to={`/projects/${projectId}/board?task=${item.entity_id}`}
                        className="activity-feed-link"
                      >
                        View task
                      </Link>
                    </>
                  )}
                </div>
              </div>
            </li>
          )
        })}
      </ul>

      {activities.length < total && (
        <div className="activity-load-more">
          <button
            type="button"
            className="secondary-button"
            onClick={handleLoadMore}
            disabled={isLoadingMore}
          >
            {isLoadingMore ? 'Loading more…' : 'Load more activity'}
          </button>
        </div>
      )}
    </div>
  )
}
