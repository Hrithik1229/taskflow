import { useCallback, useEffect, useRef, useState } from 'react'
import * as taskApi from './api'

export function useTasks(projectId, params) {
  const [tasks, setTasks] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [error, setError] = useState('')
  const tasksRef = useRef(tasks)
  useEffect(() => {
    tasksRef.current = tasks
  }, [tasks])

  const paramsKey = JSON.stringify(params || {})

  const reload = useCallback(async () => {
    if (!projectId) {
      setTasks([])
      setIsLoading(false)
      setIsRefreshing(false)
      return
    }
    if (tasksRef.current.length === 0) {
      setIsLoading(true)
    } else {
      setIsRefreshing(true)
    }
    setError('')
    try {
      const response = await taskApi.listTasks(projectId, params)
      setTasks(response.items)
    } catch (requestError) {
      setError(
        taskApi.getTaskErrorMessage(requestError, 'Tasks could not be loaded.'),
      )
    } finally {
      setIsLoading(false)
      setIsRefreshing(false)
    }
  }, [projectId, params])

  useEffect(() => {
    let active = true
    if (tasksRef.current.length === 0) {
      setIsLoading(true)
    } else {
      setIsRefreshing(true)
    }
    taskApi
      .listTasks(projectId, params)
      .then((response) => {
        if (active) {
          setTasks(response.items)
        }
      })
      .catch((requestError) => {
        if (active) {
          setError(
            taskApi.getTaskErrorMessage(
              requestError,
              'Tasks could not be loaded.',
            ),
          )
        }
      })
      .finally(() => {
        if (active) {
          setIsLoading(false)
          setIsRefreshing(false)
        }
      })
    return () => {
      active = false
    }
  }, [projectId, paramsKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const move = useCallback(
    async (task, status, position, reviewerId = null) => {
      const previousTasks = tasks
      const reordered = [...tasks]
      const sourceIndex = reordered.findIndex((item) => item.id === task.id)
      if (sourceIndex < 0) {
        return
      }
      const [moving] = reordered.splice(sourceIndex, 1)
      const sourceColumn = reordered
        .filter((item) => item.status === task.status)
        .sort((a, b) => a.position - b.position)
        .map((item, index) => ({ ...item, position: index }))
      const destinationTasks = reordered.filter(
        (item) => item.status === status,
      )
      const insertAt = Math.max(0, Math.min(position, destinationTasks.length))
      destinationTasks.splice(insertAt, 0, { ...moving, status })
      const updates = new Map()
      destinationTasks.forEach((item, index) => {
        updates.set(item.id, { ...item, status, position: index })
      })
      sourceColumn.forEach((item) => updates.set(item.id, item))
      setTasks(
        reordered
          .map((item) => updates.get(item.id) || item)
          .concat([{ ...moving, status, position: insertAt }]),
      )
      try {
        await taskApi.moveTask(task.id, {
          status,
          position: insertAt,
          expected_version: task.version,
          ...(reviewerId ? { reviewer_id: reviewerId } : {}),
        })
        await reload()
      } catch (requestError) {
        setTasks(previousTasks)
        if (requestError?.response?.status === 409) {
          await reload()
        }
        throw requestError
      }
    },
    [tasks, reload],
  )

  return { tasks, setTasks, isLoading, isRefreshing, error, reload, move }
}

export function useDashboardSummary() {
  const [summary, setSummary] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  const reload = useCallback(async () => {
    setIsLoading(true)
    setError('')
    try {
      setSummary(await taskApi.getDashboardSummary())
    } catch (requestError) {
      setError(
        taskApi.getTaskErrorMessage(
          requestError,
          'Task summary could not be loaded.',
        ),
      )
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    let active = true
    taskApi
      .getDashboardSummary()
      .then((result) => {
        if (active) setSummary(result)
      })
      .catch((requestError) => {
        if (active) {
          setError(
            taskApi.getTaskErrorMessage(
              requestError,
              'Task summary could not be loaded.',
            ),
          )
        }
      })
      .finally(() => {
        if (active) setIsLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  return { summary, isLoading, error, reload }
}
