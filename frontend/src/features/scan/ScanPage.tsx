import { useState } from 'react'
import { Link } from 'react-router-dom'

import { startScan } from '../../api/client'

export function ScanPage() {
  const [days, setDays] = useState(30)
  const [limit, setLimit] = useState(500)
  const [status, setStatus] = useState<string | null>(null)
  const [complete, setComplete] = useState(false)

  const scan = async () => {
    setStatus('Finding messages…')
    setComplete(false)
    try {
      const result = await startScan({ scan_id: crypto.randomUUID(), days, max_messages: limit })
      setStatus(`Read ${result.processed_count} messages. Classification and grouping are complete.`)
      setComplete(true)
    } catch {
      setStatus('Gmail access is unavailable. Connect or reconnect Gmail, then try again.')
    }
  }

  return (
    <main className="page page--narrow" id="main-content">
      <p className="context-line">Bounded scan</p>
      <h1>Choose how much mail to read.</h1>
      <p className="page-intro">Start small. You can scan another period later without duplicating messages.</p>
      <div className="field-row">
        <label>Recent days<input type="number" min="1" max="365" value={days} onChange={(event) => setDays(Number(event.target.value))} /></label>
        <label>Message limit<input type="number" min="1" max="500" value={limit} onChange={(event) => setLimit(Number(event.target.value))} /></label>
      </div>
      <button className="primary-action" type="button" onClick={scan}>Scan email</button>
      {status && <p className="notice" role="status">{status}</p>}
      {complete && <Link className="inline-link" to="/review">Review subscriptions</Link>}
    </main>
  )
}

