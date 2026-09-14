import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { getActionPlan, type ActionPlanView } from '../../api/client'

const methodNames: Record<string, string> = {
  rfc8058: 'One-click web request',
  mailto: 'Unsubscribe email',
  browser: 'Website',
}

export function ConfirmationPage() {
  const { planId = '' } = useParams()
  const [plan, setPlan] = useState<ActionPlanView | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void getActionPlan(planId).then(setPlan, () => setError('This action plan is no longer available.'))
  }, [planId])

  if (error) return <main className="page" id="main-content"><p role="alert">{error}</p><Link to="/review">Return to review</Link></main>
  if (!plan) return <main className="page" id="main-content"><p role="status">Preparing confirmation…</p></main>

  const groupedItems = plan.items.reduce<Record<string, typeof plan.items>>((groups, item) => {
    groups[item.method] = [...(groups[item.method] ?? []), item]
    return groups
  }, {})

  return (
    <main className="page" id="main-content">
      <p className="context-line">Final review</p>
      <h1>Confirm each destination before anything is sent.</h1>
      <p className="page-intro">Website actions open in a separate isolated browser and stop for sign-in, CAPTCHA, another website, or an unclear choice.</p>
      <div className="plan-groups">
        {Object.entries(groupedItems).map(([method, items]) => (
          <section key={method} className="plan-group">
            <h2>{methodNames[method] ?? method}</h2>
            <ul>{items.map((item) => <li key={item.candidate_id}><strong>{item.sender}</strong><span>{item.subject}</span><span>{item.target_display}</span></li>)}</ul>
          </section>
        ))}
      </div>
      <p className="notice">Execution remains disabled until the method-specific safety checks are installed in the next build step.</p>
      <button className="primary-action" type="button" disabled>Unsubscribe from {plan.items.length} lists</button>
    </main>
  )
}
