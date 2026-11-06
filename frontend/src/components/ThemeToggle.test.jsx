import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { ThemeProvider } from '../context/ThemeContext'
import ThemeToggle from './ThemeToggle'

describe('ThemeToggle', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
  })

  afterEach(() => {
    cleanup()
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
  })

  it('renders with accessible label and toggles between light and dark', async () => {
    const user = userEvent.setup()
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>,
    )

    const toggle = screen.getByRole('button', {
      name: /Switch to dark theme/i,
    })
    expect(toggle).toBeInTheDocument()
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')

    await user.click(toggle)

    expect(
      screen.getByRole('button', { name: /Switch to light theme/i }),
    ).toBeInTheDocument()
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(localStorage.getItem('taskflow_theme')).toBe('dark')

    await user.click(
      screen.getByRole('button', { name: /Switch to light theme/i }),
    )

    expect(
      screen.getByRole('button', { name: /Switch to dark theme/i }),
    ).toBeInTheDocument()
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(localStorage.getItem('taskflow_theme')).toBe('light')
  })

  it('works safely even when rendered outside ThemeProvider', async () => {
    const user = userEvent.setup()
    render(<ThemeToggle />)

    const toggle = screen.getByRole('button', {
      name: /Switch to dark theme/i,
    })
    expect(toggle).toBeInTheDocument()

    // Clicking should not crash
    await user.click(toggle)
    expect(toggle).toBeInTheDocument()
  })
})

