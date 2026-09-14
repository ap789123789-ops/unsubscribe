import { useEffect, useState } from 'react'

import { getHealth } from './api/client'
import './styles.css'

type BackendState = 'checking' | 'ready' | 'unavailable'

export function App() {
  const [backendState, setBackendState] = useState<BackendState>('checking')

  useEffect(() => {
    void getHealth().then(
      () => setBackendState('ready'),
      () => setBackendState('unavailable'),
    )
  }, [])

  return (
    <main className="shell">
      <header className="masthead">
        <span className="mark" aria-hidden="true">U</span>
        <span>Unsubscribe Desk</span>
      </header>
      <section className="intro" aria-labelledby="page-title">
        <p className="kicker">Local Gmail review</p>
        <h1 id="page-title">Clear the mail you no longer want.</h1>
        <p className="lede">
          Review subscriptions first. Nothing leaves your account until you confirm it.
        </p>
        <div className={`readiness readiness--${backendState}`} role="status">
          <span className="readiness__dot" aria-hidden="true" />
          {backendState === 'checking' && 'Checking local backend…'}
          {backendState === 'ready' && 'Backend ready'}
          {backendState === 'unavailable' && 'Backend unavailable'}
        </div>
      </section>
    </main>
  )
}

