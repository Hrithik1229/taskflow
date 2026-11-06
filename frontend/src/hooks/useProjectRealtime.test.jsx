import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import useProjectRealtime from './useProjectRealtime'
import { createClientMutationId } from '../realtime/mutations'

const socketModule = vi.hoisted(() => ({
  socket: null,
  token: 'access-token',
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ token: socketModule.token }),
}))

vi.mock('../realtime/socket', () => ({
  connectRealtimeSocket: vi.fn(() => socketModule.socket),
  getRealtimeSocket: vi.fn(() => socketModule.socket),
}))

function createSocket() {
  const listeners = new Map()
  return {
    connected: false,
    emit: vi.fn(),
    on: vi.fn((eventName, listener) => {
      const eventListeners = listeners.get(eventName) || new Set()
      eventListeners.add(listener)
      listeners.set(eventName, eventListeners)
    }),
    off: vi.fn((eventName, listener) => {
      if (listener) listeners.get(eventName)?.delete(listener)
      else listeners.delete(eventName)
    }),
    trigger(eventName, payload) {
      for (const listener of listeners.get(eventName) || []) {
        listener(payload)
      }
    },
    listeners,
  }
}

function Probe({ onEvent, onRecover, onRemoved }) {
  const { status, error } = useProjectRealtime('project-1', {
    onEvent,
    onRecover,
    onRemoved,
  })
  return (
    <div>
      <span>{status}</span>
      <span>{error}</span>
    </div>
  )
}

describe('useProjectRealtime', () => {
  beforeEach(() => {
    socketModule.socket = createSocket()
    socketModule.token = 'access-token'
  })

  afterEach(() => cleanup())

  it('joins after connect, rejoins on reconnect, and refetches after each join', () => {
    const onRecover = vi.fn()
    render(<Probe onRecover={onRecover} />)

    act(() => socketModule.socket.trigger('connect'))
    expect(socketModule.socket.emit).toHaveBeenLastCalledWith(
      'join_project',
      { project_id: 'project-1' },
      expect.any(Function),
    )
    act(() =>
      socketModule.socket.emit.mock.calls.at(-1)[2]({
        ok: true,
        project_id: 'project-1',
      }),
    )
    expect(screen.getByText('connected')).toBeInTheDocument()
    expect(onRecover).toHaveBeenCalledTimes(1)

    act(() => socketModule.socket.trigger('disconnect'))
    expect(screen.getByText('reconnecting')).toBeInTheDocument()
    act(() => socketModule.socket.trigger('connect'))
    act(() =>
      socketModule.socket.emit.mock.calls.at(-1)[2]({
        ok: true,
        project_id: 'project-1',
      }),
    )
    expect(onRecover).toHaveBeenCalledTimes(2)
  })

  it('deduplicates event ids and ignores its own mutation echo', () => {
    const onEvent = vi.fn()
    render(<Probe onEvent={onEvent} />)
    const handler = socketModule.socket.listeners.get('task_updated').values().next()
      .value

    act(() => {
      handler({ event_id: 'evt-1', task: { id: 'task-1' } })
      handler({ event_id: 'evt-1', task: { id: 'task-1' } })
    })
    expect(onEvent).toHaveBeenCalledTimes(1)

    const mutationId = createClientMutationId()
    act(() =>
      handler({
        event_id: 'evt-2',
        client_mutation_id: mutationId,
        task: { id: 'task-1' },
      }),
    )
    expect(onEvent).toHaveBeenCalledTimes(1)
  })

  it('reports join errors and cleans up listeners and room membership', () => {
    render(<Probe />)
    act(() => socketModule.socket.trigger('connect'))
    act(() =>
      socketModule.socket.emit.mock.calls.at(-1)[2]({
        ok: false,
        error: 'forbidden',
      }),
    )
    expect(screen.getByText('error')).toBeInTheDocument()
    expect(
      screen.getByText('You no longer have access to this project.'),
    ).toBeInTheDocument()

    act(() => socketModule.socket.trigger('connect'))
    act(() =>
      socketModule.socket.emit.mock.calls.at(-1)[2]({
        ok: true,
        project_id: 'project-1',
      }),
    )
    socketModule.socket.connected = true
    cleanup()
    expect(socketModule.socket.listeners.get('connect').size).toBe(0)
    expect(socketModule.socket.emit).toHaveBeenCalledWith(
      'leave_project',
      { project_id: 'project-1' },
    )
  })
})
