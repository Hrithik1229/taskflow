import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthContext } from '../context/AuthContext'
import AppShell from './AppShell'

function renderShell() {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <AuthContext.Provider
        value={{
          user: {
            id: 'user-id',
            username: 'Taylor',
            email: 'taylor@example.com',
          },
          logout: vi.fn(),
        }}
      >
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/dashboard" element={<h1>Workspace content</h1>} />
          </Route>
        </Routes>
      </AuthContext.Provider>
    </MemoryRouter>,
  )
}

describe('AppShell', () => {
  afterEach(() => cleanup())

  it('provides skip navigation, active nav and a user menu', () => {
    renderShell()

    expect(
      screen.getByRole('link', { name: 'Skip to content' }),
    ).toHaveAttribute('href', '#main-content')
    expect(screen.getByRole('link', { name: 'Dashboard' })).toHaveClass(
      'sidebar-link--active',
    )
    fireEvent.click(screen.getByText('Taylor'))
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Workspace content' }),
    ).toBeInTheDocument()
  })

  it('traps focus in the mobile drawer and restores focus after Escape', async () => {
    renderShell()
    const toggle = screen.getByRole('button', { name: 'Open navigation menu' })
    await userEvent.setup().click(toggle)

    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(document.activeElement).toHaveAttribute('href', '/dashboard')
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toHaveTextContent('Dashboard')

    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() =>
      expect(toggle).toHaveAttribute('aria-expanded', 'false'),
    )
    expect(document.activeElement).toBe(toggle)
  })
})
