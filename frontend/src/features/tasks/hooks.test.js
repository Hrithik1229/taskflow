import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as taskApi from './api'
import { useTasks } from './hooks'

vi.mock('./api', () => ({
  listTasks: vi.fn(),
  moveTask: vi.fn(),
  getTaskErrorMessage: vi.fn((_error, fallback) => fallback),
}))

const firstTask = {
  id: 'task-a',
  status: 'todo',
  position: 0,
  version: 3,
}

const secondTask = {
  id: 'task-b',
  status: 'todo',
  position: 1,
  version: 1,
}

describe('useTasks move', () => {
  beforeEach(() => {
    taskApi.listTasks.mockResolvedValue({
      items: [firstTask, secondTask],
      total: 2,
      limit: 500,
      offset: 0,
    })
  })

  it('sends the expected version and rolls back an optimistic move on failure', async () => {
    const params = {}
    const { result } = renderHook(() => useTasks('project-id', params))
    await waitFor(() => expect(result.current.tasks).toHaveLength(2))

    taskApi.moveTask.mockRejectedValue(new Error('Network failed'))
    await act(async () => {
      await expect(result.current.move(firstTask, 'review', 0)).rejects.toThrow(
        'Network failed',
      )
    })

    expect(taskApi.moveTask).toHaveBeenCalledWith('task-a', {
      status: 'review',
      position: 0,
      expected_version: 3,
    })
    expect(result.current.tasks).toEqual([firstTask, secondTask])
  })

  it('reconciles from the server after a successful move', async () => {
    const params = {}
    const movedTasks = [
      { ...firstTask, status: 'review', position: 0, version: 4 },
      { ...secondTask, position: 0, version: 2 },
    ]
    const { result } = renderHook(() => useTasks('project-id', params))
    await waitFor(() => expect(result.current.tasks).toHaveLength(2))
    taskApi.moveTask.mockResolvedValue({ task: movedTasks[0], affected: [] })
    taskApi.listTasks.mockResolvedValueOnce({
      items: movedTasks,
      total: 2,
      limit: 500,
      offset: 0,
    })

    await act(async () => {
      await result.current.move(firstTask, 'review', 0)
    })

    expect(result.current.tasks).toEqual(movedTasks)
  })

  it('sends the selected reviewer with a move into Review', async () => {
    const params = {}
    const { result } = renderHook(() => useTasks('project-id', params))
    await waitFor(() => expect(result.current.tasks).toHaveLength(2))
    taskApi.moveTask.mockResolvedValue({ task: firstTask, affected: [] })

    await act(async () => {
      await result.current.move(firstTask, 'review', 0, 'reviewer-id')
    })

    expect(taskApi.moveTask).toHaveBeenCalledWith('task-a', {
      status: 'review',
      position: 0,
      expected_version: 3,
      reviewer_id: 'reviewer-id',
    })
  })
})
