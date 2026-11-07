import { describe, expect, it } from 'vitest'
import { applyTaskEvent } from './realtime'

describe('drag and drop & real-time task mutations', () => {
  const initialTasks = [
    { id: 'task-1', title: 'Task 1', status: 'todo', position: 0, version: 1 },
    { id: 'task-2', title: 'Task 2', status: 'todo', position: 1, version: 1 },
    { id: 'task-3', title: 'Task 3', status: 'in_progress', position: 0, version: 1 },
  ]

  it('correctly handles task_created events', () => {
    const newTask = {
      id: 'task-4',
      title: 'Task 4',
      status: 'todo',
      position: 2,
      version: 1,
    }
    const result = applyTaskEvent(initialTasks, 'task_created', { task: newTask })
    expect(result.tasks).toHaveLength(4)
    expect(result.tasks.find((t) => t.id === 'task-4')).toBeDefined()
  })

  it('correctly handles task_updated events without duplicating cards', () => {
    const updated = {
      id: 'task-1',
      title: 'Task 1 - renamed',
      status: 'todo',
      position: 0,
      version: 2,
    }
    const result = applyTaskEvent(initialTasks, 'task_updated', { task: updated })
    expect(result.tasks).toHaveLength(3)
    const task = result.tasks.find((t) => t.id === 'task-1')
    expect(task?.title).toBe('Task 1 - renamed')
    expect(task?.version).toBe(2)
  })

  it('correctly handles task_moved events with sibling position updates', () => {
    const moved = {
      id: 'task-1',
      title: 'Task 1',
      status: 'in_progress',
      position: 1,
      version: 2,
    }
    const affected = [{ id: 'task-2', position: 0, version: 2 }]
    const result = applyTaskEvent(initialTasks, 'task_moved', {
      task: moved,
      affected,
    })
    expect(result.tasks).toHaveLength(3)
    const t1 = result.tasks.find((t) => t.id === 'task-1')
    expect(t1?.status).toBe('in_progress')
    expect(t1?.position).toBe(1)
    const t2 = result.tasks.find((t) => t.id === 'task-2')
    expect(t2?.position).toBe(0)
  })

  it('correctly handles task_deleted events', () => {
    const result = applyTaskEvent(initialTasks, 'task_deleted', {
      task: { id: 'task-2', version: 2 },
    })
    expect(result.tasks).toHaveLength(2)
    expect(result.tasks.find((t) => t.id === 'task-2')).toBeUndefined()
  })

  it('triggers refetch flag when version mismatch or unknown event occurs', () => {
    const result = applyTaskEvent(initialTasks, 'unknown_event', {})
    expect(result.shouldRefetch).toBe(true)
  })
})

