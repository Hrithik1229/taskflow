import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getAccessToken,
  setAccessToken,
  setUnauthorizedHandler,
} from '../api/client'
import * as authApi from '../api/auth'
import { useToast } from './ToastContext.js'
import { AuthContext } from './AuthContext'
import {
  connectRealtimeSocket,
  disconnectRealtimeSocket,
} from '../realtime/socket'
import { clearPendingMutations } from '../realtime/mutations'

export function AuthProvider({ children }) {
  const navigate = useNavigate()
  const { showToast } = useToast()
  const [token, setToken] = useState(() => getAccessToken())
  const [user, setUser] = useState(null)
  const [isLoading, setIsLoading] = useState(Boolean(getAccessToken()))

  const clearSession = useCallback(() => {
    setAccessToken(null)
    setToken(null)
    setUser(null)
    disconnectRealtimeSocket()
    clearPendingMutations()
  }, [])

  const handleUnauthorized = useCallback(() => {
    clearSession()
    showToast('Your session expired. Please sign in again.', 'error')
    navigate('/login', { replace: true })
  }, [clearSession, navigate, showToast])

  useEffect(() => {
    setUnauthorizedHandler(handleUnauthorized)
    return () => setUnauthorizedHandler(undefined)
  }, [handleUnauthorized])

  useEffect(() => {
    let active = true
    const storedToken = getAccessToken()
    if (!storedToken) {
      return () => {
        active = false
      }
    }

    authApi
      .getCurrentUser()
      .then((profile) => {
        if (active) {
          setUser(profile)
        }
      })
      .catch(() => {
        if (active) {
          clearSession()
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
  }, [clearSession])

  useEffect(() => {
    if (token) {
      connectRealtimeSocket(token)
    } else {
      disconnectRealtimeSocket()
    }
    return () => {
      if (!token) disconnectRealtimeSocket()
    }
  }, [token])

  const login = useCallback(async (credentials) => {
    const response = await authApi.login(credentials)
    setAccessToken(response.access_token)
    setToken(response.access_token)
    try {
      const profile = await authApi.getCurrentUser()
      setUser(profile)
      return profile
    } catch (error) {
      setAccessToken(null)
      setToken(null)
      setUser(null)
      throw error
    }
  }, [])

  const register = useCallback(
    async (credentials) => {
      await authApi.register(credentials)
      return login({
        email: credentials.email,
        password: credentials.password,
      })
    },
    [login],
  )

  const logout = useCallback(() => {
    clearSession()
    navigate('/login', { replace: true })
  }, [clearSession, navigate])

  const value = useMemo(
    () => ({ user, token, isLoading, login, register, logout }),
    [user, token, isLoading, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
