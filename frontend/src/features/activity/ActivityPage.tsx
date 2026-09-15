import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import {
  cancelBrowser,
  getBrowserSession,
  listPlanActions,
  resumeBrowser,
  takeOverBrowser,
  type ActionView,
  type BrowserSessionView,
} from '../../api/client'

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
    detail: 'The action paused before an ambiguous or unsafe browser step.',
  },
  failed: { label: 'Not submitted', detail: 'The action did not reach a confirmed submission.' },
  reviewed: { label: 'Stopped', detail: 'The browser action was stopped without another click.' },
}

export function ActivityPage() {
  const { planId = '' } = useParams()
  const [actions, setActions] = useState<ActionView[]>([])
  const [intervention, setIntervention] = useState<BrowserSessionView | null>(null)
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState('')
  const [error, setError] = useState<string | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const triggers = useRef(new Map<string, HTMLButtonElement>())
  const rows = useRef(new Map<string, HTMLLIElement>())
  const pendingFocus = useRef<string | null>(null)

  useEffect(() => {
    void listPlanActions(planId).then(setActions, () => {
      setError('Action activity could not be loaded.')
    }).finally(() => setLoading(false))
  }, [planId])

  useEffect(() => {
    if (intervention) headingRef.current?.focus()
  }, [intervention])

  useEffect(() => {
    if (intervention || !pendingFocus.current) return
    const actionId = pendingFocus.current
    const trigger = triggers.current.get(actionId)
    const target = trigger?.isConnected ? trigger : rows.current.get(actionId)
    target?.focus()
    if (document.activeElement === target) pendingFocus.current = null
  }, [actions, intervention])

  const updateAction = (id: string, state: string) => {
    setActions((current) => current.map((action) => (
      action.id === id ? { ...action, state } : action
    )))
  }

  const closeIntervention = () => {
    const actionId = intervention?.action_id
    if (actionId) pendingFocus.current = actionId
    setIntervention(null)
  }

  const openIntervention = async (action: ActionView) => {
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
      updateAction(action.id, action.state)
      setStatus(`Browser action is now ${stateCopy[action.state]?.label ?? action.state}.`)
      if (action.state !== 'needs_user') closeIntervention()
      else setIntervention(await getBrowserSession(intervention.id))
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Resume failed.')
    }
  }

  const stop = async () => {
    if (!intervention) return
    try {
      const action = await cancelBrowser(intervention.id)
      updateAction(action.id, action.state)
      setStatus('The browser action was stopped. No final click will be retried automatically.')
      closeIntervention()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Stop failed.')
    }
  }

  return (
    <main className="page" id="main-content">
      <p className="context-line">Unsubscribe activity</p>
      <h1>Every action keeps an honest status.</h1>
      <p className="page-intro">
        “Request sent” is intentionally separate from “Unsubscribe confirmed.” Uncertain browser
        outcomes always pause instead of silently clicking again.
      </p>
      <p className="visually-hidden" role="status" aria-live="polite">{status}</p>
      {loading && <p role="status">Loading action activity…</p>}
      {error && <p className="notice notice--error" role="alert">{error}</p>}
      {!loading && actions.length === 0 && <p className="notice">No actions have been confirmed for this plan.</p>}
      <ol className="activity-list">
        {actions.map((action) => {
          const copy = stateCopy[action.state] ?? { label: action.state, detail: 'Status recorded.' }
          return (
            <li
              className={`activity-row activity-row--${action.state}`}
              key={action.id}
              ref={(node) => {
                if (node) rows.current.set(action.id, node)
                else rows.current.delete(action.id)
              }}
              tabIndex={-1}
            >
              <div>
                <span className="method-pill">{action.method}</span>
                <h2>{copy.label}</h2>
                <p>{copy.detail}</p>
              </div>
              {action.state === 'needs_user' && action.browser_session_id && (
                <button
                  className="secondary-action"
                  type="button"
                  ref={(node) => {
                    if (node) triggers.current.set(action.id, node)
                    else triggers.current.delete(action.id)
                  }}
                  onClick={() => openIntervention(action)}
                >
                  Review browser blocker
                </button>
              )}
            </li>
          )
        })}
      </ol>
      <Link className="inline-link" to="/review">Return to subscriptions</Link>

      {intervention && (
        <div className="dialog-backdrop">
          <section
            className="evidence-dialog intervention-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="browser-blocker-title"
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
              <button className="text-button" type="button" onClick={closeIntervention}>Close</button>
            </div>
          </section>
        </div>
      )}
    </main>
  )
}
