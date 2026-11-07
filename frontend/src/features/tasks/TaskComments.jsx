import { useEffect, useState } from 'react'
import Avatar from '../../components/Avatar'
import {
  createComment,
  getTaskErrorMessage,
  listComments,
} from './api'
import { getRealtimeSocket } from '../../realtime/socket'

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

export default function TaskComments({ taskId }) {
  const [comments, setComments] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [newComment, setNewComment] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [formError, setFormError] = useState('')

  const loadComments = async () => {
    if (!taskId) return
    setIsLoading(true)
    setError('')
    try {
      const data = await listComments(taskId, { limit: 100 })
      setComments(data.items || [])
    } catch (err) {
      setError(getTaskErrorMessage(err, 'Failed to load comments.'))
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    let active = true
    if (!taskId) return undefined
    listComments(taskId, { limit: 100 })
      .then((data) => {
        if (active) {
          setComments(data.items || [])
        }
      })
      .catch((err) => {
        if (active) {
          setError(getTaskErrorMessage(err, 'Failed to load comments.'))
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
  }, [taskId])

  useEffect(() => {
    const socket = getRealtimeSocket()
    if (!socket) return undefined

    const handleCommentAdded = (payload) => {
      if (String(payload?.task_id) === String(taskId) && payload?.comment) {
        setComments((prev) => {
          if (prev.some((c) => c.id === payload.comment.id)) return prev
          return [...prev, payload.comment]
        })
      }
    }

    socket.on('comment_added', handleCommentAdded)
    return () => {
      socket.off('comment_added', handleCommentAdded)
    }
  }, [taskId])

  const handleSubmit = async (e) => {
    e.preventDefault()
    const content = newComment.trim()
    if (!content) {
      setFormError('Comment cannot be empty.')
      return
    }
    if (content.length > 2000) {
      setFormError('Comment must be 2000 characters or fewer.')
      return
    }

    setIsSubmitting(true)
    setFormError('')
    try {
      const created = await createComment(taskId, { content })
      setNewComment('')
      setComments((prev) => {
        if (prev.some((c) => c.id === created.id)) return prev
        return [...prev, created]
      })
    } catch (err) {
      setFormError(getTaskErrorMessage(err, 'Could not post comment.'))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="task-comments-section" aria-labelledby="task-comments-heading">
      <h3 id="task-comments-heading">
        Discussion {comments.length > 0 && `(${comments.length})`}
      </h3>

      <div className="task-comments-list" role="feed" aria-label="Task comments">
        {isLoading && comments.length === 0 ? (
          <p className="task-comments-loading">Loading comments…</p>
        ) : error ? (
          <div className="task-comments-error" role="alert">
            <p>{error}</p>
            <button
              type="button"
              className="secondary-button"
              onClick={loadComments}
            >
              Try again
            </button>
          </div>
        ) : comments.length === 0 ? (
          <p className="task-comments-empty">No comments yet. Start the conversation!</p>
        ) : (
          comments.map((comment) => (
            <article key={comment.id} className="task-comment-item">
              <Avatar
                name={comment.author?.username || 'User'}
                size="small"
              />
              <div className="task-comment-content">
                <header className="task-comment-header">
                  <span className="task-comment-author">
                    {comment.author?.username || 'User'}
                  </span>
                  <time
                    dateTime={comment.created_at}
                    title={new Date(comment.created_at).toLocaleString()}
                    className="task-comment-time"
                  >
                    {relativeTime(comment.created_at)}
                  </time>
                </header>
                <p className="task-comment-body">{comment.content}</p>
              </div>
            </article>
          ))
        )}
      </div>

      <form className="task-comment-form" onSubmit={handleSubmit}>
        <div className="form-field">
          <label htmlFor="task-new-comment">Add a comment</label>
          <textarea
            id="task-new-comment"
            rows={3}
            placeholder="Write a comment… (1–2000 characters)"
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            disabled={isSubmitting}
            maxLength={2000}
            required
          />
        </div>
        {formError && (
          <p className="form-server-error" role="alert">
            {formError}
          </p>
        )}
        <div className="task-comment-form-actions">
          <span className="character-count" aria-live="polite">
            {newComment.length}/2000
          </span>
          <button
            type="submit"
            className="primary-button"
            disabled={isSubmitting || !newComment.trim()}
          >
            {isSubmitting ? 'Posting…' : 'Comment'}
          </button>
        </div>
      </form>
    </section>
  )
}
