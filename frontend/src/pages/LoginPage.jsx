import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.js'
import ThemeToggle from '../components/ThemeToggle'

function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}

function apiErrorMessage(error) {
  const detail = error.response?.data?.detail
  if (typeof detail === 'string') {
    return detail
  }
  if (Array.isArray(detail) && typeof detail[0]?.msg === 'string') {
    return detail[0].msg
  }
  return 'We could not sign you in. Please try again.'
}

export default function LoginPage() {
  const { login } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [errors, setErrors] = useState({})
  const [serverError, setServerError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    const validation = {}
    if (!isValidEmail(email.trim())) {
      validation.email = 'Enter a valid email address.'
    }
    if (password.length < 8 || password.length > 128) {
      validation.password = 'Password must be between 8 and 128 characters.'
    }
    setErrors(validation)
    setServerError('')
    if (Object.keys(validation).length) {
      return
    }

    setIsSubmitting(true)
    try {
      await login({ email: email.trim(), password })
      const destination = location.state?.from
      const path = destination?.pathname?.startsWith('/')
        ? `${destination.pathname}${destination.search || ''}${destination.hash || ''}`
        : '/dashboard'
      navigate(path, { replace: true })
    } catch (error) {
      setServerError(apiErrorMessage(error))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="login-title">
        <div className="auth-card-top">
          <Link className="auth-brand" to="/" aria-label="TaskFlow home">
            <span className="brand-mark" aria-hidden="true">
              T
            </span>
            <span>TaskFlow</span>
          </Link>
          <ThemeToggle />
        </div>
        <p className="eyebrow">WELCOME BACK</p>
        <h1 id="login-title">Sign in to your account</h1>
        <p className="auth-subtitle">Pick up where your team left off.</p>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <div className="form-field">
            <label htmlFor="login-email">Email</label>
            <input
              id="login-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              aria-invalid={Boolean(errors.email)}
              aria-describedby={errors.email ? 'login-email-error' : undefined}
              required
            />
            {errors.email && (
              <span className="field-error" id="login-email-error">
                {errors.email}
              </span>
            )}
          </div>
          <div className="form-field">
            <label htmlFor="login-password">Password</label>
            <div className="password-input">
              <input
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                aria-invalid={Boolean(errors.password)}
                aria-describedby={
                  errors.password ? 'login-password-error' : undefined
                }
                required
              />
              <button
                className="password-toggle"
                type="button"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                aria-pressed={showPassword}
                onClick={() => setShowPassword((visible) => !visible)}
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
            {errors.password && (
              <span className="field-error" id="login-password-error">
                {errors.password}
              </span>
            )}
          </div>

          {serverError && (
            <p className="form-server-error" role="alert">
              {serverError}
            </p>
          )}
          <button
            className="primary-button"
            type="submit"
            disabled={isSubmitting}
          >
            {isSubmitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="auth-switch">
          New to TaskFlow? <Link to="/register">Create an account</Link>
        </p>
      </section>
    </main>
  )
}
