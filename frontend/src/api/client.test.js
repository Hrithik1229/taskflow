import { afterEach, describe, expect, it, vi } from 'vitest'
import apiClient, {
  getAccessToken,
  setAccessToken,
  setUnauthorizedHandler,
} from './client'

function unauthorizedAdapter(config) {
  return Promise.reject({
    config,
    response: { status: 401, config },
  })
}

describe('API authentication interceptor', () => {
  afterEach(() => {
    setUnauthorizedHandler(undefined)
    setAccessToken(null)
  })

  it('clears the session and notifies the auth store on protected 401', async () => {
    const handleUnauthorized = vi.fn()
    setAccessToken('expired-token')
    setUnauthorizedHandler(handleUnauthorized)

    await expect(
      apiClient.get('/auth/me', { adapter: unauthorizedAdapter }),
    ).rejects.toMatchObject({ response: { status: 401 } })

    expect(getAccessToken()).toBeNull()
    expect(sessionStorage.getItem('taskflow_access_token')).toBeNull()
    expect(handleUnauthorized).toHaveBeenCalledOnce()
  })

  it('does not clear the session for a rejected login submission', async () => {
    const handleUnauthorized = vi.fn()
    setAccessToken('still-valid-token')
    setUnauthorizedHandler(handleUnauthorized)

    await expect(
      apiClient.post('/auth/login', {}, { adapter: unauthorizedAdapter }),
    ).rejects.toMatchObject({ response: { status: 401 } })

    expect(getAccessToken()).toBe('still-valid-token')
    expect(handleUnauthorized).not.toHaveBeenCalled()
  })
})
