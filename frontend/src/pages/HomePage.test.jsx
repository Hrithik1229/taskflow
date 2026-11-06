import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { getHealth } from '../api/health'
import HomePage from './HomePage'

vi.mock('../api/health', () => ({
  getHealth: vi.fn(),
}))

describe('HomePage health status', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('shows the connected state from the health response', async () => {
    getHealth.mockResolvedValue({ status: 'ok' })

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Backend connected',
    )
  })

  it('shows a failed state when the health request fails', async () => {
    getHealth.mockRejectedValue(new Error('Network unavailable'))

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Backend unavailable',
    )
  })
})
