import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

import { getHealth } from '../api/client'

export function AppShell() {
  const [backend, setBackend] = useState('Checking backend…')
  useEffect(() => {
    void getHealth().then(
      () => setBackend('Backend ready'),
      () => setBackend('Backend unavailable'),
    )
  }, [])

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <header className="app-header">
        <NavLink className="brand" to="/review" aria-label="Unsubscribe Desk home">
          <span className="brand__mark" aria-hidden="true">U</span>
          <span>Unsubscribe Desk</span>
        </NavLink>
        <div className="header-actions">
          <span className="backend-status" role="status">{backend}</span>
          <nav aria-label="Primary navigation">
            <NavLink to="/scan">Scan</NavLink>
            <NavLink to="/review">Review</NavLink>
            <NavLink to="/settings">Settings</NavLink>
          </nav>
        </div>
      </header>
      <Outlet />
    </div>
  )
}
