import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getHealth } from '../api/health'
import ThemeToggle from '../components/ThemeToggle'

export default function HomePage() {
  const [status, setStatus] = useState('loading')

  useEffect(() => {
    let active = true

    getHealth()
      .then((health) => {
        if (active) {
          setStatus(health.status === 'ok' ? 'connected' : 'failed')
        }
      })
      .catch(() => {
        if (active) {
          setStatus('failed')
        }
      })

    return () => {
      active = false
    }
  }, [])

  const messages = {
    loading: 'Checking backend connection…',
    connected: 'Backend connected',
    failed: 'Backend unavailable',
  }

  return (
    <main className="home">
      <div className="brand-mark" aria-hidden="true">
        T
      </div>
      <nav className="home-nav" aria-label="Account">
        <ThemeToggle />
        <Link to="/login">Sign in</Link>
        <Link className="home-nav-primary" to="/register">
          Get started
        </Link>
      </nav>
      <p className="eyebrow">TEAM WORK, IN FLOW</p>
      <h1>Make progress visible.</h1>
      <p className="intro">
        A shared space for teams to organize work and move it forward together.
      </p>
      <p
        className={`health health--${status}`}
        role="status"
        aria-live="polite"
      >
        <span className="health-dot" aria-hidden="true" />
        {messages[status]}
      </p>
    </main>
  )
}
