import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.js'
import Avatar from '../components/Avatar'
import ThemeToggle from '../components/ThemeToggle'

const FOCUSABLE =
  'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
const MOBILE_QUERY = '(max-width: 760px)'

export default function AppShell() {
  const { user, logout } = useAuth()
  const [isMobile, setIsMobile] = useState(
    () =>
      typeof window !== 'undefined' &&
      window.matchMedia?.(MOBILE_QUERY).matches === true,
  )
  const [drawerOpen, setDrawerOpen] = useState(false)
  const drawerRef = useRef(null)
  const toggleRef = useRef(null)

  useEffect(() => {
    const mediaQuery = window.matchMedia?.(MOBILE_QUERY)
    if (!mediaQuery) {
      return undefined
    }
    const updateViewport = (event) => {
      setIsMobile(event.matches)
      if (!event.matches) {
        setDrawerOpen(false)
      }
    }
    mediaQuery.addEventListener('change', updateViewport)
    return () => mediaQuery.removeEventListener('change', updateViewport)
  }, [])

  useEffect(() => {
    if (!drawerOpen) {
      return undefined
    }
    const toggleElement = toggleRef.current
    const links = drawerRef.current?.querySelectorAll(FOCUSABLE) || []
    links[0]?.focus()

    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        event.preventDefault()
        setDrawerOpen(false)
        return
      }
      if (event.key !== 'Tab' || !drawerRef.current) {
        return
      }
      const items = [...drawerRef.current.querySelectorAll(FOCUSABLE)]
      if (!items.length) {
        event.preventDefault()
      } else if (event.shiftKey && document.activeElement === items[0]) {
        event.preventDefault()
        items.at(-1).focus()
      } else if (!event.shiftKey && document.activeElement === items.at(-1)) {
        event.preventDefault()
        items[0].focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      toggleElement?.focus()
    }
  }, [drawerOpen])

  function closeDrawer() {
    setDrawerOpen(false)
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      {drawerOpen && (
        <button
          className="drawer-backdrop"
          type="button"
          aria-label="Close navigation"
          onClick={closeDrawer}
        />
      )}
      <aside
        className={`app-sidebar${drawerOpen ? ' app-sidebar--open' : ''}`}
        id="primary-navigation"
        ref={drawerRef}
        aria-label="Primary navigation"
        aria-hidden={isMobile && !drawerOpen}
        inert={isMobile && !drawerOpen}
      >
        <NavLink
          className="sidebar-brand"
          to="/dashboard"
          onClick={closeDrawer}
        >
          <span className="brand-mark" aria-hidden="true">
            T
          </span>
          <span>TaskFlow</span>
        </NavLink>
        <nav className="sidebar-nav" aria-label="Workspace">
          <NavLink
            to="/dashboard"
            end
            className={({ isActive }) =>
              `sidebar-link${isActive ? ' sidebar-link--active' : ''}`
            }
            onClick={closeDrawer}
          >
            <span aria-hidden="true">⌂</span>
            Dashboard
          </NavLink>
        </nav>
        <div className="sidebar-footer">
          <span className="sidebar-footer-label">TEAM WORK, IN FLOW</span>
        </div>
      </aside>

      <div className="app-main">
        <header className="app-topbar">
          <button
            ref={toggleRef}
            className="icon-button mobile-nav-toggle"
            type="button"
            aria-label={
              drawerOpen ? 'Close navigation menu' : 'Open navigation menu'
            }
            aria-expanded={drawerOpen}
            aria-controls="primary-navigation"
            onClick={() => setDrawerOpen((open) => !open)}
          >
            <span aria-hidden="true">{drawerOpen ? '×' : '☰'}</span>
          </button>
          <div className="topbar-spacer" />
          <div className="topbar-actions">
            <ThemeToggle />
            <details className="user-menu">
              <summary aria-label="User menu">
                <Avatar name={user?.username || 'User'} size="small" />
                <span>{user?.username}</span>
                <span className="user-menu-chevron" aria-hidden="true">
                  ▾
                </span>
              </summary>
              <div className="user-menu-panel">
                <span className="user-menu-email">{user?.email}</span>
                <button type="button" onClick={logout}>
                  Sign out
                </button>
              </div>
            </details>
          </div>
        </header>
        <main className="app-content" id="main-content" tabIndex="-1">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
