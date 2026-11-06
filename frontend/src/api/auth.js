import apiClient from './client'

export async function register(credentials) {
  const { data } = await apiClient.post('/auth/register', credentials)
  return data
}

export async function login(credentials) {
  const { data } = await apiClient.post('/auth/login', credentials)
  return data
}

export async function getCurrentUser() {
  const { data } = await apiClient.get('/auth/me')
  return data
}
