function applyVersionedPatch(current, patch) {
  if (patch.version <= current.version) return current
  if (patch.version > current.version + 1) return null
  return { ...current, ...patch }
}

export function applyTaskEvent(tasks, eventName, payload) {
  const incomingTask = payload?.task
  if (!incomingTask?.id) return { tasks, shouldRefetch: true }
  const taskIndex = tasks.findIndex((task) => task.id === incomingTask.id)

  if (eventName === 'task_created') {
    if (taskIndex < 0) {
      return { tasks: [...tasks, incomingTask], shouldRefetch: false }
    }
    const updatedTask = applyVersionedPatch(tasks[taskIndex], incomingTask)
    if (!updatedTask) return { tasks, shouldRefetch: true }
    if (updatedTask === tasks[taskIndex]) {
      return { tasks, shouldRefetch: false }
    }
    return {
      tasks: tasks.map((task, index) =>
        index === taskIndex ? updatedTask : task,
      ),
      shouldRefetch: false,
    }
  }

  if (taskIndex < 0) return { tasks, shouldRefetch: true }

  if (eventName === 'task_updated') {
    const updatedTask = applyVersionedPatch(tasks[taskIndex], incomingTask)
    if (!updatedTask) return { tasks, shouldRefetch: true }
    if (updatedTask === tasks[taskIndex]) {
      return { tasks, shouldRefetch: false }
    }
    return {
      tasks: tasks.map((task, index) =>
        index === taskIndex ? updatedTask : task,
      ),
      shouldRefetch: false,
    }
  }

  if (eventName !== 'task_moved' && eventName !== 'task_deleted') {
    return { tasks, shouldRefetch: true }
  }

  const patches = [incomingTask, ...(payload.affected || [])]
  const taskById = new Map(tasks.map((task) => [task.id, task]))
  const updatedById = new Map()
  for (const patch of patches) {
    const current = taskById.get(patch.id)
    if (!current) return { tasks, shouldRefetch: true }
    const updated = applyVersionedPatch(current, patch)
    if (!updated) return { tasks, shouldRefetch: true }
    updatedById.set(patch.id, updated)
  }

  if (eventName === 'task_deleted') {
    return {
      tasks: tasks
        .filter((task) => task.id !== incomingTask.id)
        .map((task) => updatedById.get(task.id) || task),
      shouldRefetch: false,
    }
  }

  return {
    tasks: tasks.map((task) => updatedById.get(task.id) || task),
    shouldRefetch: false,
  }
}
