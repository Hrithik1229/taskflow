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

export async function listComments(taskId, params = {}) {
  const { data } = await apiClient.get(`/tasks/${taskId}/comments`, { params })
  return data
}

export async function createComment(taskId, payload) {
  const { data } = await apiClient.post(
    `/tasks/${taskId}/comments`,
    payload,
    mutationConfig(),
  )
  return data
}

export async function listNotifications(params = {}) {
  const { data } = await apiClient.get('/notifications', { params })
  return data
}

export async function markNotificationRead(notificationId) {
  const { data } = await apiClient.patch(`/notifications/${notificationId}/read`)
  return data
}

export async function markAllNotificationsRead() {
  const { data } = await apiClient.patch('/notifications/read-all')
  return data
}

export async function listProjectActivity(projectId, params = {}) {
  const { data } = await apiClient.get(`/projects/${projectId}/activity`, {
    params,
  })
  return data
}

export async function getRecentActivity(params = {}) {
  const { data } = await apiClient.get('/activity/recent', { params })
  return data
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
