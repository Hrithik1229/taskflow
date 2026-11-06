import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.js'

export default function ProtectedRoute({ children }) {
  const { user, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <main className="auth-loading" role="status">
        Restoring your session…
      </main>
    )
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }
  return children
}
