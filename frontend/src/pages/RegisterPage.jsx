import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
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
  return 'We could not create your account. Please try again.'
}

export default function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [errors, setErrors] = useState({})
  const [serverError, setServerError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    const validation = {}
    const normalizedUsername = username.trim()
    if (normalizedUsername.length < 3 || normalizedUsername.length > 50) {
      validation.username = 'Username must be between 3 and 50 characters.'
    }
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
      await register({
        username: normalizedUsername,
        email: email.trim(),
        password,
      })
      navigate('/dashboard', { replace: true })
    } catch (error) {
      setServerError(apiErrorMessage(error))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="register-title">
        <div className="auth-card-top">
          <Link className="auth-brand" to="/" aria-label="TaskFlow home">
            <span className="brand-mark" aria-hidden="true">
              T
            </span>
            <span>TaskFlow</span>
          </Link>
          <ThemeToggle />
        </div>
        <p className="eyebrow">GET STARTED</p>
        <h1 id="register-title">Create your account</h1>
        <p className="auth-subtitle">Start making progress together.</p>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <div className="form-field">
            <label htmlFor="register-username">Username</label>
            <input
              id="register-username"
              type="text"
              autoComplete="username"
              minLength={3}
              maxLength={50}
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              aria-invalid={Boolean(errors.username)}
              aria-describedby={
                errors.username ? 'register-username-error' : undefined
              }
              required
            />
            {errors.username && (
              <span className="field-error" id="register-username-error">
                {errors.username}
              </span>
            )}
          </div>
          <div className="form-field">
            <label htmlFor="register-email">Email</label>
            <input
              id="register-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              aria-invalid={Boolean(errors.email)}
              aria-describedby={
                errors.email ? 'register-email-error' : undefined
              }
              required
            />
            {errors.email && (
              <span className="field-error" id="register-email-error">
                {errors.email}
              </span>
            )}
          </div>
          <div className="form-field">
            <label htmlFor="register-password">Password</label>
            <div className="password-input">
              <input
                id="register-password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="new-password"
                minLength={8}
                maxLength={128}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                aria-invalid={Boolean(errors.password)}
                aria-describedby={
                  errors.password
                    ? 'register-password-error'
                    : 'password-guidance'
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
            <span className="field-hint" id="password-guidance">
              Use 8 to 128 characters.
            </span>
            {errors.password && (
              <span className="field-error" id="register-password-error">
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
            {isSubmitting ? 'Creating account…' : 'Create account'}
          </button>
        </form>

        <p className="auth-switch">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </section>
    </main>
  )
}
