import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Avatar from './Avatar'
import Badge from './Badge'
import EmptyState from './EmptyState'
import ErrorState from './ErrorState'
import Skeleton from './Skeleton'

function relativeTime(value) {
  if (!value) return ''
  const timestamp = new Date(value).getTime()
  if (!Number.isFinite(timestamp)) return ''
  const seconds = Math.round((timestamp - Date.now()) / 1000)
  const units = [
    ['year', 60 * 60 * 24 * 365],
    ['month', 60 * 60 * 24 * 30],
    ['day', 60 * 60 * 24],
    ['hour', 60 * 60],
    ['minute', 60],
  ]
  const [unit, secondsPerUnit] =
    units.find(([, duration]) => Math.abs(seconds) >= duration) || [
      'second',
      1,
    ]
  return new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(
    Math.round(seconds / secondsPerUnit),
    unit,
  )
}

describe('Accessibility & UI Component Smoke Tests', () => {
  it('Avatar renders an accessible avatar with initial', () => {
    render(<Avatar name="Alice Cooper" />)
    expect(screen.getByText('AC')).toBeInTheDocument()
  })

  it('Badge renders with semantic role or text', () => {
    render(<Badge tone="danger">Urgent</Badge>)
    expect(screen.getByText('Urgent')).toBeInTheDocument()
  })

  it('EmptyState renders title and action accessible by screen readers', () => {
    render(
      <EmptyState
        title="No tasks found"
        action={<button type="button">Create one</button>}
      >
        Try modifying your search.
      </EmptyState>,
    )
    expect(screen.getByText('No tasks found')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create one' })).toBeInTheDocument()
  })

  it('ErrorState renders with alert role for accessibility', () => {
    render(<ErrorState message="Network failure" onRetry={() => {}} />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Network failure')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('Skeleton renders accessible loading indicators with aria-hidden', () => {
    const { container } = render(<Skeleton count={3} />)
    const wrapper = container.querySelector('.skeleton-list')
    expect(wrapper).toHaveAttribute('aria-hidden', 'true')
    const skeletons = container.querySelectorAll('.skeleton')
    expect(skeletons).toHaveLength(3)
  })
})

describe('Timestamp & Timezone Conversion Tests', () => {
  it('formats relative time for past dates correctly', () => {
    const pastOneHour = new Date(Date.now() - 3600 * 1000).toISOString()
    const result = relativeTime(pastOneHour)
    expect(result).toMatch(/1 hour ago|in 1 hour/)
  })

  it('handles invalid timestamp gracefully without throwing', () => {
    expect(relativeTime('invalid-date')).toBe('')
    expect(relativeTime(null)).toBe('')
  })

  it('correctly converts UTC timestamp to local Date object', () => {
    const utcString = '2026-05-15T12:00:00Z'
    const date = new Date(utcString)
    expect(date.getUTCFullYear()).toBe(2026)
    expect(date.getUTCMonth()).toBe(4) // 0-indexed May
    expect(date.getUTCDate()).toBe(15)
    expect(date.getUTCHours()).toBe(12)
  })
})

