import { describe, expect, it } from 'vitest'
import { applyTaskEvent } from './realtime'

const initialTasks = [
  { id: 'moving', title: 'Moving task', status: 'todo', position: 0, version: 1 },
  { id: 'sibling', title: 'Sibling', status: 'todo', position: 1, version: 1 },
]

describe('applyTaskEvent', () => {
  it('creates, updates, moves, and deletes tasks without duplicating cards', () => {
    const created = {
      ...initialTasks[0],
      id: 'new',
      version: 1,
    }
    const afterCreate = applyTaskEvent(initialTasks, 'task_created', {
      task: created,
    })
    expect(afterCreate.tasks).toHaveLength(3)

    const updated = applyTaskEvent(afterCreate.tasks, 'task_updated', {
      task: { ...created, title: 'Updated', version: 2 },
    })
    expect(updated.tasks.find((task) => task.id === 'new')).toMatchObject({
      title: 'Updated',
      version: 2,
    })

    const moved = applyTaskEvent(initialTasks, 'task_moved', {
      task: {
        ...initialTasks[0],
        status: 'in_progress',
        position: 0,
        version: 2,
      },
      affected: [{ id: 'sibling', position: 0, version: 2 }],
    })
    expect(moved.tasks).toEqual([
      { ...initialTasks[0], status: 'in_progress', version: 2 },
      { ...initialTasks[1], position: 0, version: 2 },
    ])

    const deleted = applyTaskEvent(moved.tasks, 'task_deleted', {
      task: { ...initialTasks[0], version: 3 },
      affected: [{ id: 'sibling', position: 0, version: 3 }],
    })
    expect(deleted.tasks).toEqual([
      { ...initialTasks[1], position: 0, version: 3 },
    ])
  })

  it('ignores stale versions and requests a refetch for unknown tasks or version gaps', () => {
    const stale = applyTaskEvent(initialTasks, 'task_updated', {
      task: { ...initialTasks[0], title: 'Stale', version: 1 },
    })
    expect(stale.tasks).toBe(initialTasks)
    expect(stale.shouldRefetch).toBe(false)

    const unknown = applyTaskEvent(initialTasks, 'task_deleted', {
      task: { id: 'missing', version: 2 },
    })
    expect(unknown.shouldRefetch).toBe(true)

    const gap = applyTaskEvent(initialTasks, 'task_updated', {
      task: { ...initialTasks[0], version: 4 },
    })
    expect(gap.shouldRefetch).toBe(true)
  })
})
