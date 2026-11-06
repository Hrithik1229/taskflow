import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { setAccessToken } from '../api/client'
import * as authApi from '../api/auth'
import AppShell from '../layouts/AppShell'
import ProtectedRoute from '../components/ProtectedRoute'
import PublicOnlyRoute from '../components/PublicOnlyRoute'
import { AuthProvider } from '../context/AuthContext.jsx'
import { ToastProvider } from '../context/ToastContext.jsx'
import DashboardPage from './DashboardPage'
import LoginPage from './LoginPage'
import RegisterPage from './RegisterPage'

vi.mock('../api/auth', () => ({
  login: vi.fn(),
  register: vi.fn(),
  getCurrentUser: vi.fn(),
}))

vi.mock('../features/projects/api', () => ({
  listProjects: vi.fn().mockResolvedValue([]),
  createProject: vi.fn(),
  getProject: vi.fn(),
  updateProject: vi.fn(),
  deleteProject: vi.fn(),
  listMembers: vi.fn(),
  addMember: vi.fn(),
  updateMemberRole: vi.fn(),
  removeMember: vi.fn(),
  getErrorMessage: vi.fn(
    (error, fallback) => error?.response?.data?.detail || fallback,
  ),
}))

const authenticatedUser = {
  id: 'user-id',
  username: 'Taylor',
  email: 'taylor@example.test',
  created_at: '2026-01-01T00:00:00Z',
}

function TestRoutes({ initialPath = '/login' }) {
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      <ToastProvider>
        <AuthProvider>
          <Routes>
            <Route
              path="/login"
              element={
                <PublicOnlyRoute>
                  <LoginPage />
                </PublicOnlyRoute>
              }
            />
            <Route
              path="/register"
              element={
                <PublicOnlyRoute>
                  <RegisterPage />
                </PublicOnlyRoute>
              }
            />
            <Route element={<AppShell />}>
              <Route
                path="/dashboard"
                element={
                  <ProtectedRoute>
                    <DashboardPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/private"
                element={
                  <ProtectedRoute>
                    <h1>Private destination</h1>
                  </ProtectedRoute>
                }
              />
            </Route>
          </Routes>
        </AuthProvider>
      </ToastProvider>
    </MemoryRouter>
  )
}

describe('authentication pages and routes', () => {
  beforeEach(() => {
    sessionStorage.clear()
    setAccessToken(null)
    authApi.login.mockReset()
    authApi.register.mockReset()
    authApi.getCurrentUser.mockReset()
  })

  afterEach(() => cleanup())

  it('shows inline validation messages on login', async () => {
    const user = userEvent.setup()
    render(<TestRoutes />)

    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(screen.getByText('Enter a valid email address.')).toBeInTheDocument()
    expect(
      screen.getByText('Password must be between 8 and 128 characters.'),
    ).toBeInTheDocument()
  })

  it('logs in, stores the session, and navigates to dashboard', async () => {
    const user = userEvent.setup()
    authApi.login.mockResolvedValue({ access_token: 'access-token' })
    authApi.getCurrentUser.mockResolvedValue(authenticatedUser)
    render(<TestRoutes />)

    await user.type(screen.getByLabelText('Email'), 'taylor@example.test')
    await user.type(screen.getByLabelText('Password'), 'my-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(
      await screen.findByRole('heading', { name: 'Welcome, Taylor' }),
    ).toBeInTheDocument()
    expect(sessionStorage.getItem('taskflow_access_token')).toBe('access-token')
  })

  it('shows a server error on login failure', async () => {
    const user = userEvent.setup()
    authApi.login.mockRejectedValue({
      response: { data: { detail: 'Invalid email or password.' } },
    })
    render(<TestRoutes />)

    await user.type(screen.getByLabelText('Email'), 'taylor@example.test')
    await user.type(screen.getByLabelText('Password'), 'wrong-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Invalid email or password.',
    )
  })

  it('redirects unauthenticated users to login and remembers destination', async () => {
    render(<TestRoutes initialPath="/private" />)

    expect(
      await screen.findByRole('heading', { name: 'Sign in to your account' }),
    ).toBeInTheDocument()
    const user = userEvent.setup()
    authApi.login.mockResolvedValue({ access_token: 'access-token' })
    authApi.getCurrentUser.mockResolvedValue(authenticatedUser)
    await user.type(screen.getByLabelText('Email'), 'taylor@example.test')
    await user.type(screen.getByLabelText('Password'), 'my-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(
      await screen.findByRole('heading', { name: 'Private destination' }),
    ).toBeInTheDocument()
  })

  it('redirects authenticated users away from login and register', async () => {
    sessionStorage.setItem('taskflow_access_token', 'stored-token')
    setAccessToken('stored-token')
    authApi.getCurrentUser.mockResolvedValue(authenticatedUser)

    render(<TestRoutes />)
    expect(
      await screen.findByRole('heading', { name: 'Welcome, Taylor' }),
    ).toBeInTheDocument()

    cleanup()
    render(<TestRoutes initialPath="/register" />)
    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Welcome, Taylor' }),
      ).toBeInTheDocument()
    })
  })

  it('clears an invalid stored session and returns to login', async () => {
    sessionStorage.setItem('taskflow_access_token', 'expired-token')
    setAccessToken('expired-token')
    authApi.getCurrentUser.mockRejectedValue({
      response: {
        status: 401,
        data: { detail: 'Invalid or expired access token.' },
      },
    })
    render(<TestRoutes initialPath="/dashboard" />)

    expect(
      await screen.findByRole('heading', { name: 'Sign in to your account' }),
    ).toBeInTheDocument()
    expect(sessionStorage.getItem('taskflow_access_token')).toBeNull()
  })

  it('registers then signs in and navigates to dashboard', async () => {
    const user = userEvent.setup()
    authApi.register.mockResolvedValue({ id: authenticatedUser.id })
    authApi.login.mockResolvedValue({ access_token: 'new-token' })
    authApi.getCurrentUser.mockResolvedValue(authenticatedUser)
    render(<TestRoutes initialPath="/register" />)

    await user.type(screen.getByLabelText('Username'), 'Taylor')
    await user.type(screen.getByLabelText('Email'), 'taylor@example.test')
    await user.type(screen.getByLabelText('Password'), 'a-valid-password')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(authApi.register).toHaveBeenCalledOnce()
    expect(authApi.login).toHaveBeenCalledOnce()
    expect(
      await screen.findByRole('heading', { name: 'Welcome, Taylor' }),
    ).toBeInTheDocument()
  })

  it('logs out and clears the stored token', async () => {
    const user = userEvent.setup()
    sessionStorage.setItem('taskflow_access_token', 'stored-token')
    setAccessToken('stored-token')
    authApi.getCurrentUser.mockResolvedValue(authenticatedUser)
    render(<TestRoutes initialPath="/dashboard" />)

    await screen.findByText('Taylor')
    await user.click(screen.getByText('Taylor'))
    await user.click(screen.getByRole('button', { name: 'Sign out' }))

    expect(
      await screen.findByRole('heading', { name: 'Sign in to your account' }),
    ).toBeInTheDocument()
    expect(sessionStorage.getItem('taskflow_access_token')).toBeNull()
  })

  it('toggles password visibility accessibly', async () => {
    const user = userEvent.setup()
    render(<TestRoutes />)
    const password = screen.getByLabelText('Password')
    const toggle = screen.getByRole('button', { name: 'Show password' })

    await user.click(toggle)

    expect(password).toHaveAttribute('type', 'text')
    expect(
      screen.getByRole('button', { name: 'Hide password' }),
    ).toHaveAttribute('aria-pressed', 'true')
  })
})
