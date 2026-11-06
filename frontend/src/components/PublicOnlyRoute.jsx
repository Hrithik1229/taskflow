import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.js'

export default function PublicOnlyRoute({ children }) {
  const { user, isLoading } = useAuth()
  const location = useLocation()
  if (isLoading) {
    return (
      <main className="auth-loading" role="status">
        Restoring your session…
      </main>
    )
  }
  const destination = location.state?.from
  const redirectTo = destination?.pathname?.startsWith('/')
    ? `${destination.pathname}${destination.search || ''}${destination.hash || ''}`
    : '/dashboard'
  return user ? <Navigate to={redirectTo} replace /> : children
}
