import React from 'react'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ConfirmDialog from './ConfirmDialog'

function DialogHarness({ onConfirm = vi.fn() }) {
  const [open, setOpen] = React.useState(false)
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open confirmation
      </button>
      {open && (
        <ConfirmDialog
          title="Remove member?"
          message="The member will lose access."
          confirmLabel="Remove"
          isDestructive
          onClose={() => setOpen(false)}
          onConfirm={onConfirm}
        />
      )}
    </>
  )
}

describe('ConfirmDialog', () => {
  afterEach(() => cleanup())

  it('traps keyboard focus and restores focus on cancel', async () => {
    const user = userEvent.setup()
    render(<DialogHarness />)
    const trigger = screen.getByRole('button', { name: 'Open confirmation' })
    await user.click(trigger)
    const dialog = screen.getByRole('dialog', { name: 'Remove member?' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')

    await user.keyboard('{Shift>}{Tab}{/Shift}')
    expect(screen.getByRole('button', { name: 'Remove' })).toHaveFocus()
    await user.keyboard('{Escape}')

    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
    expect(trigger).toHaveFocus()
  })

  it('invokes confirmation when the destructive action is chosen', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    render(<DialogHarness onConfirm={onConfirm} />)

    await user.click(screen.getByRole('button', { name: 'Open confirmation' }))
    await user.click(screen.getByRole('button', { name: 'Remove' }))

    expect(onConfirm).toHaveBeenCalledOnce()
  })
})
