import { useCallback, useEffect, useRef, useState } from 'react'
import * as projectApi from './api'

export function useProjects() {
  const [projects, setProjects] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  const reload = useCallback(async () => {
    setIsLoading(true)
    setError('')
    try {
      setProjects(await projectApi.listProjects())
    } catch (requestError) {
      setError(
        projectApi.getErrorMessage(
          requestError,
          'Projects could not be loaded.',
        ),
      )
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    let active = true
    projectApi
      .listProjects()
      .then((result) => {
        if (active) {
          setProjects(result)
        }
      })
      .catch((requestError) => {
        if (active) {
          setError(
            projectApi.getErrorMessage(
              requestError,
              'Projects could not be loaded.',
            ),
          )
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
  }, [])

  const create = useCallback(async (payload) => {
    return projectApi.createProject(payload)
  }, [])

  return { projects, isLoading, error, reload, create }
}

export function useProject(projectId) {
  const [project, setProject] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const projectRef = useRef(project)

  useEffect(() => {
    projectRef.current = project
  }, [project])

  const reload = useCallback(async () => {
    if (!projectId) {
      setProject(null)
      setIsLoading(false)
      return null
    }
    if (!projectRef.current) {
      setIsLoading(true)
    }
    setError('')
    try {
      const data = await projectApi.getProject(projectId)
      setProject(data)
      return data
    } catch (requestError) {
      setError(
        projectApi.getErrorMessage(
          requestError,
          'Project could not be loaded.',
        ),
      )
      return null
    } finally {
      setIsLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    let active = true
    if (!projectId) {
      return () => {
        active = false
      }
    }
    projectApi
      .getProject(projectId)
      .then((result) => {
        if (active) {
          setProject(result)
        }
      })
      .catch((requestError) => {
        if (active) {
          setError(
            projectApi.getErrorMessage(
              requestError,
              'Project could not be loaded.',
            ),
          )
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
  }, [projectId])

  return { project, isLoading, error, reload, setProject }
}
