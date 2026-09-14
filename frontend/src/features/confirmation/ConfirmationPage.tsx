import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import {
  beginGoogleOAuth,
  confirmActionPlan,
  getAccount,
  getActionPlan,
  type ActionPlanView,
  type ActionView,
} from '../../api/client'

const gmailSendScope = 'https://www.googleapis.com/auth/gmail.send'

const methodNames: Record<string, string> = {
  rfc8058: 'One-click web request',
  mailto: 'Unsubscribe email',
  browser: 'Website',
}

const resultLabels: Record<string, string> = {
  submitted: 'Submitted — list processing is not verified',
  confirmed: 'Confirmed by destination',
  needs_user: 'Needs your review',
  failed: 'Failed',
  executing: 'In progress',
}

export function ConfirmationPage() {
  const { planId = '' } = useParams()
  const [plan, setPlan] = useState<ActionPlanView | null>(null)
  const [sendAuthorized, setSendAuthorized] = useState(false)
  const [actions, setActions] = useState<ActionView[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void getActionPlan(planId).then(async (loadedPlan) => {
      setPlan(loadedPlan)
      if (loadedPlan.items.some((item) => item.method === 'mailto')) {
        try {
          const account = await getAccount()
          setSendAuthorized(account.scopes.includes(gmailSendScope))
        } catch {
          setSendAuthorized(false)
        }
      }
    }, () => setError('This action plan is no longer available.'))
  }, [planId])

  if (error && !plan) {
    return (
      <main className="page" id="main-content">
        <p role="alert">{error}</p>
        <Link to="/review">Return to review</Link>
      </main>
    )
  }
  if (!plan) {
    return <main className="page" id="main-content"><p role="status">Preparing confirmation…</p></main>
  }

  const groupedItems = plan.items.reduce<Record<string, typeof plan.items>>((groups, item) => {
    groups[item.method] = [...(groups[item.method] ?? []), item]
    return groups
  }, {})
  const requiresSendConsent = plan.items.some((item) => item.method === 'mailto') && !sendAuthorized
  const actionsByCandidate = new Map(actions.map((action) => [action.candidate_id, action]))

  const authorizeSend = async () => {
    setBusy(true)
    setError(null)
    try {
      const start = await beginGoogleOAuth('send', `/confirm/${plan.id}`)
      window.location.assign(start.authorization_url)
    } catch {
      setError('Gmail send authorization could not start. Check the OAuth configuration.')
      setBusy(false)
    }
  }

  const confirm = async () => {
    setBusy(true)
    setError(null)
    try {
      setActions(await confirmActionPlan(plan.id, plan.digest))
    } catch (failure) {
      const message = failure instanceof Error ? failure.message : 'Confirmation failed.'
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="page" id="main-content">
      <p className="context-line">Final review</p>
      <h1>Confirm each destination before anything is sent.</h1>
      <p className="page-intro">
        A successful web request or Gmail send means submitted—not proof that the list processed
        the unsubscribe. Website actions may pause for you in an isolated browser.
      </p>
      <div className="plan-groups">
        {Object.entries(groupedItems).map(([method, items]) => (
          <section key={method} className="plan-group">
            <h2>{methodNames[method] ?? method}</h2>
            <ul>
              {items.map((item) => (
                <li key={item.candidate_id}>
                  <div><strong>{item.sender}</strong><span>{item.subject}</span></div>
                  {item.mail_preview ? (
                    <dl className="mail-preview">
                      <div><dt>To</dt><dd>{item.mail_preview.recipient}</dd></div>
                      <div><dt>Subject</dt><dd>{item.mail_preview.subject}</dd></div>
                      <div><dt>Body</dt><dd><pre>{item.mail_preview.body}</pre></dd></div>
                    </dl>
                  ) : <span>{item.target_display}</span>}
                  <span>{actionsByCandidate.has(item.candidate_id)
                    ? resultLabels[actionsByCandidate.get(item.candidate_id)!.state]
                    : 'Ready for confirmation'}</span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
      {requiresSendConsent && (
        <p className="notice">
          Gmail requires a second consent screen for unsubscribe emails. The desktop flow requests
          the combined read-and-send scopes, then returns here; it never grants inbox modification.
        </p>
      )}
      {error && <p className="notice notice--error" role="alert">{error}</p>}
      {actions.length > 0 ? (
        <Link className="inline-link" to={`/activity/${plan.id}`}>View activity</Link>
      ) : (
        <button
          className="primary-action"
          type="button"
          disabled={busy}
          onClick={requiresSendConsent ? authorizeSend : confirm}
        >
          {busy
            ? 'Working…'
            : requiresSendConsent
              ? 'Authorize Gmail sending'
              : `Confirm unsubscribe from ${plan.items.length} ${plan.items.length === 1 ? 'list' : 'lists'}`}
        </button>
      )}
    </main>
  )
}
