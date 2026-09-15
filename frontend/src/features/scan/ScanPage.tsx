import { useState } from 'react'
import { Link } from 'react-router-dom'

import { startScan } from '../../api/client'

export function ScanPage() {
  const [days, setDays] = useState(30)
  const [limit, setLimit] = useState(500)
  const [scanId, setScanId] = useState(() => crypto.randomUUID())
  const [status, setStatus] = useState<string | null>(null)
  const [complete, setComplete] = useState(false)
  const [pending, setPending] = useState(false)

  const changeBounds = (update: () => void) => {
    update()
    setScanId(crypto.randomUUID())
    setStatus(null)
    setComplete(false)
  }

  const scan = async () => {
    if (pending) return
    setPending(true)
    setStatus('Finding messages…')
    setComplete(false)
    try {
      const result = await startScan({ scan_id: scanId, days, max_messages: limit })
      setStatus(`Read ${result.processed_count} messages. Classification and grouping are complete.`)
      setComplete(true)
    } catch (error) {
      setStatus(
        error instanceof Error
          ? error.message
          : 'Scan failed. Check the local backend and retry.',
      )
    } finally {
      setPending(false)
    }
  }

  return (
    <main className="page page--narrow" id="main-content">
      <p className="context-line">Bounded scan</p>
      <h1>Choose how much mail to read.</h1>
      <p className="page-intro">Start small. You can scan another period later without duplicating messages.</p>
      <div className="field-row">
        <label>
          Recent days
          <input
            type="number"
            min="1"
            max="365"
            value={days}
            disabled={pending}
            onChange={(event) => changeBounds(() => setDays(Number(event.target.value)))}
          />
        </label>
        <label>
          Message limit
          <input
            type="number"
            min="1"
            max="500"
            value={limit}
            disabled={pending}
            onChange={(event) => changeBounds(() => setLimit(Number(event.target.value)))}
          />
        </label>
      </div>
      <button
        className="primary-action"
        type="button"
        disabled={pending}
        aria-busy={pending}
        onClick={scan}
      >
        Scan email
      </button>
      {status && <p className="notice" role="status">{status}</p>}
      {complete && <Link className="inline-link" to="/review">Review subscriptions</Link>}
    </main>
  )
}
