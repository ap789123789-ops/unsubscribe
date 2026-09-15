import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import {
  beginGoogleOAuth,
  cancelBrowser,
  getAccount,
  getBrowserSession,
  listActions,
  resumeBrowser,
  retryAction,
  takeOverBrowser,
  type ActivityActionView,
  type BrowserSessionView,
} from '../../api/client'

const GMAIL_SEND_SCOPE = 'https://www.googleapis.com/auth/gmail.send'

const stateCopy: Record<string, { label: string; detail: string }> = {
  executing: { label: 'Working', detail: 'The reviewed action is in progress.' },
  confirmed: {
    label: 'Unsubscribe confirmed',
    detail: 'The sender explicitly acknowledged the request.',
  },
  submitted: {
    label: 'Request sent',
    detail: 'The request left the app, but sender processing was not explicitly confirmed.',
  },
  needs_user: {
    label: 'Your help is needed',
    detail: 'The action paused before an ambiguous or unsafe step.',
  },
  failed: { label: 'Not submitted', detail: 'The action did not reach a confirmed submission.' },
  reviewed: { label: 'Stopped', detail: 'The action was stopped without another attempt.' },
}

type ActivityFilter = 'all' | 'attention' | 'working' | 'submitted' | 'confirmed'

const needsAttention = (action: ActivityActionView) => (
  action.state === 'needs_user' || action.state === 'failed' || action.state === 'reviewed'
)

const senderName = (sender: string) => sender.split('<')[0]?.trim() || sender

export function ActivityPage() {
  const { planId } = useParams()
  const [actions, setActions] = useState<ActivityActionView[]>([])
  const [filter, setFilter] = useState<ActivityFilter>('all')
  const [intervention, setIntervention] = useState<BrowserSessionView | null>(null)
  const [repairAction, setRepairAction] = useState<ActivityActionView | null>(null)
  const [sendAuthorized, setSendAuthorized] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState<string | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const dialogRef = useRef<HTMLElement>(null)
  const rows = useRef(new Map<string, HTMLLIElement>())
  const pendingFocus = useRef<string | null>(null)

  const refreshActions = useCallback(async () => {
    setActions(await listActions(planId))
  }, [planId])

  useEffect(() => {
    void listActions(planId).then(setActions, () => {
      setError('Action activity could not be loaded.')
    }).finally(() => setLoading(false))
  }, [planId])

  useEffect(() => {
    void getAccount().then(
      (account) => setSendAuthorized(account.connected && account.scopes.includes(GMAIL_SEND_SCOPE)),
      () => setSendAuthorized(false),
    )
  }, [])

  useEffect(() => {
    if (!planId) return undefined
    const events = new EventSource(`/events/actions/${encodeURIComponent(planId)}`)
    const updateFromEvent = () => {
      void refreshActions().catch(() => setError('A live activity update could not be read.'))
    }
    events.addEventListener('action-state', updateFromEvent)
    return () => events.close()
  }, [planId, refreshActions])

  useEffect(() => {
    if (intervention || repairAction) headingRef.current?.focus()
  }, [intervention, repairAction])

  useEffect(() => {
    if (intervention || repairAction || !pendingFocus.current) return
    const target = rows.current.get(pendingFocus.current)
    target?.focus()
    if (document.activeElement === target) pendingFocus.current = null
  }, [actions, intervention, repairAction])

  const closeDialog = () => {
    const actionId = intervention?.action_id ?? repairAction?.id
    if (actionId) pendingFocus.current = actionId
    setIntervention(null)
    setRepairAction(null)
  }

  const openIntervention = async (action: ActivityActionView) => {
    if (!action.browser_session_id) return
    setError(null)
    try {
      setIntervention(await getBrowserSession(action.browser_session_id))
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Browser session unavailable.')
    }
  }

  const takeOver = async () => {
    if (!intervention) return
    try {
      setIntervention(await takeOverBrowser(intervention.id))
      setStatus('The guarded browser is now in front. Network protections remain active.')
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Takeover failed.')
    }
  }

  const resume = async () => {
    if (!intervention) return
    try {
      const action = await resumeBrowser(intervention.id)
      await refreshActions()
      setStatus(`Browser action is now ${stateCopy[action.state]?.label ?? action.state}.`)
      if (action.state !== 'needs_user') closeDialog()
      else setIntervention(await getBrowserSession(intervention.id))
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Resume failed.')
    }
  }

  const stop = async () => {
    if (!intervention) return
    try {
      await cancelBrowser(intervention.id)
      await refreshActions()
      setStatus('The browser action was stopped. No final click will be retried automatically.')
      closeDialog()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Stop failed.')
    }
  }

  const reconnectGmail = async () => {
    setError(null)
    try {
      const destination = planId ? `/activity/${planId}` : '/activity'
      const oauth = await beginGoogleOAuth('send', destination)
      window.location.assign(oauth.authorization_url)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Gmail authorization could not start.')
    }
  }

  const confirmRepair = async () => {
    if (!repairAction) return
    setBusy(true)
    setError(null)
    try {
      const updated = await retryAction(repairAction.id)
      setActions((current) => current.map((action) => action.id === updated.id ? updated : action))
      setStatus(`${senderName(updated.sender)} is now ${stateCopy[updated.state]?.label ?? updated.state}.`)
      closeDialog()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'The reviewed retry failed.')
    } finally {
      setBusy(false)
    }
  }

  const handleDialogKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      closeDialog()
      return
    }
    if (event.key !== 'Tab' || !dialogRef.current) return
    const focusable = Array.from(
      dialogRef.current.querySelectorAll<HTMLElement>('[tabindex="-1"], button:not(:disabled)'),
    )
    const first = focusable[0]
    const last = focusable.at(-1)
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last?.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first?.focus()
    }
  }

  const filteredActions = actions.filter((action) => {
    if (filter === 'attention') return needsAttention(action)
    if (filter === 'working') return action.state === 'executing'
    if (filter === 'submitted') return action.state === 'submitted'
    if (filter === 'confirmed') return action.state === 'confirmed'
    return true
  })
  const counts = {
    all: actions.length,
    attention: actions.filter(needsAttention).length,
    working: actions.filter((action) => action.state === 'executing').length,
    submitted: actions.filter((action) => action.state === 'submitted').length,
    confirmed: actions.filter((action) => action.state === 'confirmed').length,
  }

  return (
    <main className="page" id="main-content">
      <p className="context-line">{planId ? 'This unsubscribe run' : 'All unsubscribe activity'}</p>
      <h1>Every action keeps an honest status.</h1>
      <p className="page-intro">
        “Request sent” is intentionally separate from “Unsubscribe confirmed.” Each row shows what
        happened, the evidence we have, and the next safe action when your help is needed.
      </p>
      <p className="visually-hidden" role="status" aria-live="polite">{status}</p>
      {loading && <p role="status">Loading action activity…</p>}
      {error && <p className="notice notice--error" role="alert">{error}</p>}

      {!loading && actions.length > 0 && (
        <div className="activity-filters" aria-label="Filter unsubscribe activity">
          {([
            ['all', 'All actions'],
            ['attention', 'Needs attention'],
            ['working', 'Working'],
            ['submitted', 'Request sent'],
            ['confirmed', 'Confirmed'],
          ] as const).map(([value, label]) => (
            <button
              className={filter === value ? 'activity-filter activity-filter--active' : 'activity-filter'}
              key={value}
              type="button"
              aria-pressed={filter === value}
              onClick={() => setFilter(value)}
            >
              {label} <span>{counts[value]}</span>
            </button>
          ))}
        </div>
      )}

      {!loading && actions.length === 0 && (
        <p className="notice">No unsubscribe actions have been started yet.</p>
      )}
      {!loading && actions.length > 0 && filteredActions.length === 0 && (
        <p className="notice">No actions match this filter.</p>
      )}
      <ol className="activity-list">
        {filteredActions.map((action) => {
          const copy = stateCopy[action.state] ?? { label: action.state, detail: 'Status recorded.' }
          const isMailtoAuthRepair = action.method === 'mailto'
            && action.evidence_code === 'gmail_send_authorization_required'
            && action.retry_available
          return (
            <li
              aria-label={`${senderName(action.sender)}: ${copy.label}`}
              className={`activity-row activity-row--${action.state}`}
              key={action.id}
              ref={(node) => {
                if (node) rows.current.set(action.id, node)
                else rows.current.delete(action.id)
              }}
              tabIndex={-1}
            >
              <div className="activity-row__identity">
                <span className="method-pill">{action.method}</span>
                <h2>{senderName(action.sender)}</h2>
                <p>{action.subject}</p>
                <span className="activity-target">Target: {action.target_display}</span>
              </div>
              <div className="activity-row__result">
                <strong className="activity-status">{copy.label}</strong>
                <p>{action.safe_detail ?? copy.detail}</p>
                <time dateTime={action.updated_at}>
                  {new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(action.updated_at))}
                </time>
              </div>
              <div className="activity-row__repair">
                {action.state === 'needs_user' && action.browser_session_id && (
                  <button className="secondary-action" type="button" onClick={() => openIntervention(action)}>
                    Review browser blocker
                  </button>
                )}
                {action.method === 'rfc8058' && action.retry_available && (
                  <button className="secondary-action" type="button" onClick={() => setRepairAction(action)}>
                    Review one-click retry
                  </button>
                )}
                {isMailtoAuthRepair && !sendAuthorized && (
                  <button className="secondary-action" type="button" onClick={reconnectGmail}>
                    Reconnect Gmail
                  </button>
                )}
                {isMailtoAuthRepair && sendAuthorized && (
                  <button className="secondary-action" type="button" onClick={() => setRepairAction(action)}>
                    Review email send
                  </button>
                )}
              </div>
            </li>
          )
        })}
      </ol>
      <Link className="inline-link" to="/review">Return to subscriptions</Link>

      {intervention && (
        <div className="dialog-backdrop">
          <section
            ref={dialogRef}
            className="evidence-dialog intervention-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="browser-blocker-title"
            onKeyDown={handleDialogKeyDown}
          >
            <p className="context-line">Guarded browser paused</p>
            <h2 id="browser-blocker-title" ref={headingRef} tabIndex={-1}>Your help is needed</h2>
            <p>{intervention.blocker_detail}</p>
            <dl className="intervention-facts">
              <div><dt>Destination</dt><dd>{intervention.origin}</dd></div>
              <div><dt>Final click</dt><dd>{intervention.final_click_issued ? 'May have occurred' : 'Not issued'}</dd></div>
              <div><dt>Blocked requests</dt><dd>{intervention.blocked_request_count}</dd></div>
            </dl>
            <div className="dialog-actions">
              <button className="primary-action" type="button" onClick={takeOver}>Take over in browser</button>
              <button className="secondary-action" type="button" onClick={resume}>Resume automation</button>
              <button className="text-button" type="button" onClick={stop}>Stop this action</button>
              <button className="text-button" type="button" onClick={closeDialog}>Close</button>
            </div>
          </section>
        </div>
      )}

      {repairAction && (
        <div className="dialog-backdrop">
          <section
            ref={dialogRef}
            className="evidence-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="repair-title"
            onKeyDown={handleDialogKeyDown}
          >
            <p className="context-line">Reviewed retry</p>
            <h2 id="repair-title" ref={headingRef} tabIndex={-1}>
              {repairAction.method === 'mailto' ? 'Send the reviewed email?' : 'Retry the one-click request?'}
            </h2>
            <p>
              {repairAction.method === 'mailto'
                ? 'This sends the exact unsubscribe email you already reviewed. It will be attempted once.'
                : 'The sender returned a retryable error. This is the one allowed retry; an uncertain submission is never retried.'}
            </p>
            <div className="dialog-actions">
              <button className="primary-action" type="button" disabled={busy} onClick={confirmRepair}>
                {repairAction.method === 'mailto' ? 'Send reviewed email' : 'Retry one-click request'}
              </button>
              <button className="text-button" type="button" disabled={busy} onClick={closeDialog}>Cancel</button>
            </div>
          </section>
        </div>
      )}
    </main>
  )
}
