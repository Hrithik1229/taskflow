import apiClient from '../../api/client'

export async function listProjects(params = {}) {
  const { data } = await apiClient.get('/projects', { params })
  return data
}

export async function createProject(payload) {
  const { data } = await apiClient.post('/projects', payload)
  return data
}

export async function getProject(projectId) {
  const { data } = await apiClient.get(`/projects/${projectId}`)
  return data
}

export async function updateProject(projectId, payload) {
  const { data } = await apiClient.patch(`/projects/${projectId}`, payload)
  return data
}

export async function deleteProject(projectId) {
  await apiClient.delete(`/projects/${projectId}`)
}

export async function listMembers(projectId) {
  const { data } = await apiClient.get(`/projects/${projectId}/members`)
  return data
}

export async function addMember(projectId, payload) {
  const { data } = await apiClient.post(
    `/projects/${projectId}/members`,
    payload,
  )
  return data
}

export async function updateMemberRole(projectId, userId, payload) {
  const { data } = await apiClient.patch(
    `/projects/${projectId}/members/${userId}`,
    payload,
  )
  return data
}

export async function removeMember(projectId, userId) {
  await apiClient.delete(`/projects/${projectId}/members/${userId}`)
}

export function getErrorMessage(error, fallback) {
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
