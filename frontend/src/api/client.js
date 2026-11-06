import axios from 'axios'

const SESSION_TOKEN_KEY = 'taskflow_access_token'
let accessToken = sessionStorage.getItem(SESSION_TOKEN_KEY)
let unauthorizedHandler

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
})

export function setAccessToken(token) {
  accessToken = token
  if (token) {
    sessionStorage.setItem(SESSION_TOKEN_KEY, token)
  } else {
    sessionStorage.removeItem(SESSION_TOKEN_KEY)
  }
}

export function getAccessToken() {
  return accessToken
}

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler
}

apiClient.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const requestUrl = error.config?.url || ''
    const isAuthSubmission =
      requestUrl.includes('/auth/login') ||
      requestUrl.includes('/auth/register')
    if (error.response?.status === 401 && !isAuthSubmission) {
      setAccessToken(null)
      unauthorizedHandler?.()
    }
    return Promise.reject(error)
  },
)

export default apiClient
