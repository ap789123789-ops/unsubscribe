import { useState } from 'react'

import { disconnectGoogle } from '../../api/client'

export function SettingsPage() {
  const [message, setMessage] = useState<string | null>(null)
  return <main className="page page--narrow" id="main-content"><p className="context-line">Local data</p><h1>Settings</h1><p className="page-intro">Disconnecting removes the OAuth credential from your operating system credential store.</p><button className="secondary-action" type="button" onClick={async () => { await disconnectGoogle(); setMessage('Gmail disconnected.') }}>Disconnect Gmail</button>{message && <p role="status" className="notice">{message}</p>}</main>
}
