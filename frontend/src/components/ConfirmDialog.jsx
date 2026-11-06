import Modal from './Modal'

export default function ConfirmDialog({
  title,
  message,
  confirmLabel = 'Confirm',
  isDestructive = false,
  onConfirm,
  onClose,
  isLoading = false,
}) {
  return (
    <Modal
      title={title}
      onClose={onClose}
      actions={
        <>
          <button
            className="secondary-button"
            type="button"
            onClick={onClose}
            disabled={isLoading}
          >
            Cancel
          </button>
          <button
            className={isDestructive ? 'danger-button' : 'primary-button'}
            type="button"
            onClick={onConfirm}
            disabled={isLoading}
          >
            {isLoading ? 'Working…' : confirmLabel}
          </button>
        </>
      }
    >
      <p>{message}</p>
    </Modal>
  )
}
