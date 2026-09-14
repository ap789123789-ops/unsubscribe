import { useState } from 'react'

import { beginGoogleOAuth } from '../../api/client'

export function SetupPage() {
  const [error, setError] = useState<string | null>(null)

  const connect = async () => {
    setError(null)
    try {
      const start = await beginGoogleOAuth()
      window.location.assign(start.authorization_url)
    } catch {
      setError('Google OAuth is not configured. Add your desktop client file and restart the app.')
    }
  }

  return (
    <main className="page page--narrow" id="main-content">
      <p className="context-line">Private by default</p>
      <h1>Connect your inbox to begin sorting.</h1>
      <p className="page-intro">
        The app reads email content to classify it. Sanitized text is sent to OpenAI. Full email
        bodies are not stored by default.
      </p>
      <dl className="readiness-list">
        <div><dt>Local backend</dt><dd>Ready</dd></div>
        <div><dt>Gmail permission</dt><dd>Not connected</dd></div>
        <div><dt>Initial access</dt><dd>Read only</dd></div>
        <div><dt>Unsubscribe email</dt><dd>Requested only when needed</dd></div>
      </dl>
      {error && <p className="notice notice--error" role="alert">{error}</p>}
      <button className="primary-action" type="button" onClick={connect}>Connect Gmail</button>
    </main>
  )
}

