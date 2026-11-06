import { useCallback, useMemo, useState } from 'react'
import { ToastContext } from './ToastContext'

export function ToastProvider({ children }) {
  const [toast, setToast] = useState(null)

  const dismissToast = useCallback(() => setToast(null), [])
  const showToast = useCallback((message, type = 'info') => {
    setToast({ message, type, id: Date.now() })
  }, [])
  const value = useMemo(
    () => ({ showToast, dismissToast }),
    [dismissToast, showToast],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      {toast && (
        <div
          className={`toast toast--${toast.type}`}
          role={toast.type === 'error' ? 'alert' : 'status'}
          key={toast.id}
        >
          <span>{toast.message}</span>
          <button type="button" onClick={dismissToast} aria-label="Dismiss">
            ×
          </button>
        </div>
      )}
    </ToastContext.Provider>
  )
}
