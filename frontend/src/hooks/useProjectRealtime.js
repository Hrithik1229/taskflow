import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import {
  connectRealtimeSocket,
  getRealtimeSocket,
} from '../realtime/socket'
import { isOwnMutation } from '../realtime/mutations'

const PROJECT_EVENTS = [
  'task_created',
  'task_updated',
  'task_moved',
  'task_deleted',
  'comment_added',
  'member_changed',
  'notification_created',
  'project_updated',
  'project_deleted',
]
const EVENT_ID_LIMIT = 500

export default function useProjectRealtime(
  projectId,
  { onEvent, onRemoved, onRecover } = {},
) {
  const { token } = useAuth()
  const [status, setStatus] = useState('offline')
  const [error, setError] = useState('')
  const callbacks = useRef({ onEvent, onRemoved, onRecover })
  const processedEventIds = useRef(new Set())

  useEffect(() => {
    callbacks.current = { onEvent, onRemoved, onRecover }
  }, [onEvent, onRemoved, onRecover])

  const handleEvent = useCallback((eventName, payload) => {
    if (payload?.event_id) {
      if (processedEventIds.current.has(payload.event_id)) return
      processedEventIds.current.add(payload.event_id)
      if (processedEventIds.current.size > EVENT_ID_LIMIT) {
        const oldest = processedEventIds.current.values().next().value
        processedEventIds.current.delete(oldest)
      }
    }
    if (isOwnMutation(payload?.client_mutation_id)) return
    callbacks.current.onEvent?.(eventName, payload)
  }, [])

  useEffect(() => {
    if (!token || !projectId) return undefined
    const socket = connectRealtimeSocket(token)
    let joined = false
    let disposed = false

    function joinRoom() {
      setStatus('reconnecting')
      setError('')
      socket.emit('join_project', { project_id: projectId }, (ack) => {
        if (disposed) return
        if (!ack?.ok) {
          joined = false
          setStatus('error')
          setError(
            ack?.error === 'forbidden'
              ? 'You no longer have access to this project.'
              : 'Live updates could not join this project.',
          )
          if (ack?.error === 'forbidden') {
            callbacks.current.onRemoved?.(ack)
          }
          return
        }
        joined = true
        setStatus('connected')
        callbacks.current.onRecover?.()
      })
    }

    function onConnect() {
      joinRoom()
    }
    function onDisconnect() {
      joined = false
      setStatus('reconnecting')
    }
    function onConnectError() {
      joined = false
      setStatus('offline')
      setError('Live updates are offline. Reconnecting…')
    }
    function onRemoved(payload) {
      if (payload?.project_id === projectId) {
        joined = false
        callbacks.current.onRemoved?.(payload)
      }
    }

    socket.on('connect', onConnect)
    socket.on('disconnect', onDisconnect)
    socket.on('connect_error', onConnectError)
    socket.on('removed_from_project', onRemoved)
    const eventHandlers = new Map(
      PROJECT_EVENTS.map((eventName) => [
        eventName,
        (payload) => handleEvent(eventName, payload),
      ]),
    )
    for (const [eventName, handler] of eventHandlers) {
      socket.on(eventName, handler)
    }
    if (socket.connected) queueMicrotask(onConnect)

    return () => {
      disposed = true
      socket.off('connect', onConnect)
      socket.off('disconnect', onDisconnect)
      socket.off('connect_error', onConnectError)
      socket.off('removed_from_project', onRemoved)
      for (const [eventName, handler] of eventHandlers) {
        socket.off(eventName, handler)
      }
      if (joined && socket.connected) {
        socket.emit('leave_project', { project_id: projectId })
      }
    }
  }, [handleEvent, projectId, token])

  return {
    status: !token || !getRealtimeSocket() ? 'offline' : status,
    error,
  }
}
