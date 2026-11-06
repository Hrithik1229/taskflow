import apiClient from '../../api/client'
import { createClientMutationId } from '../../realtime/mutations'

function mutationConfig() {
  return {
    headers: {
      'X-Client-Mutation-Id': createClientMutationId(),
    },
  }
}

export async function listTasks(projectId, params = {}) {
  const { data } = await apiClient.get(`/projects/${projectId}/tasks`, {
    params,
  })
  return data
}

export async function listProjectMembers(projectId) {
  const { data } = await apiClient.get(`/projects/${projectId}/members`)
  return data
}

export async function getDashboardSummary() {
  const { data } = await apiClient.get('/dashboard/summary')
  return data
}

export async function getDashboardBreakdown(metric) {
  const { data } = await apiClient.get('/dashboard/summary/breakdown', {
    params: { metric },
  })
  return data
}

export async function getTask(taskId) {
  const { data } = await apiClient.get(`/tasks/${taskId}`)
  return data
}

export async function createTask(projectId, payload) {
  const { data } = await apiClient.post(
    `/projects/${projectId}/tasks`,
    payload,
    mutationConfig(),
  )
  return data
}

export async function updateTask(taskId, payload) {
  const { data } = await apiClient.patch(
    `/tasks/${taskId}`,
    payload,
    mutationConfig(),
  )
  return data
}

export async function moveTask(taskId, payload) {
  const { data } = await apiClient.patch(
    `/tasks/${taskId}/move`,
    payload,
    mutationConfig(),
  )
  return data
}

export async function deleteTask(taskId) {
  await apiClient.delete(`/tasks/${taskId}`, mutationConfig())
}

export function getTaskErrorMessage(error, fallback) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') {
    return detail
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item.msg)
      .filter(Boolean)
      .join(' ')
  }
  return fallback
}
