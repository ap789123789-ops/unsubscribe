import { useEffect, useRef, useState } from 'react'

export type Category = 'marketing' | 'unclear' | 'non_marketing'
export type Method = 'rfc8058' | 'mailto' | 'browser'

export interface ReviewCandidate {
  id: string
  revision: number
  sender: string
  representativeSubject: string
  messageCount: number
  category: Category
  confidence: number
  reason: string
  evidenceQuote: string
  method: Method
  targetDisplay: string
  dateRange: string
}

interface ReviewPageProps {
  candidates: ReviewCandidate[]
  onCreatePlan: (selected: ReviewCandidate[]) => void
  onCorrect: (id: string, revision: number, category: Category) => void
}

const categories: { id: Category; label: string; note: string }[] = [
  { id: 'marketing', label: 'Marketing', note: 'Promotions and recurring editorial mail' },
  { id: 'unclear', label: 'Unclear', note: 'Messages that need your judgment' },
  { id: 'non_marketing', label: 'Non-marketing', note: 'Transactional and personal mail' },
]

const methodLabels: Record<Method, string> = {
  rfc8058: 'One-click request',
  mailto: 'Unsubscribe email',
  browser: 'Website',
}

function senderName(sender: string) {
  return sender.split('<', 1)[0].trim()
}

export function ReviewPage({ candidates, onCreatePlan, onCorrect }: ReviewPageProps) {
  const [expanded, setExpanded] = useState<Record<Category, boolean>>({
    marketing: true,
    unclear: false,
    non_marketing: false,
  })
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [evidenceId, setEvidenceId] = useState<string | null>(null)
  const evidenceTriggers = useRef(new Map<string, HTMLButtonElement>())
  const evidenceDialog = useRef<HTMLElement>(null)
  const evidenceHeading = useRef<HTMLHeadingElement>(null)
  const pendingEvidenceFocus = useRef<string | null>(null)
  const evidence = candidates.find((candidate) => candidate.id === evidenceId)

  useEffect(() => {
    if (evidenceId) {
      evidenceHeading.current?.focus()
      return
    }
    if (pendingEvidenceFocus.current) {
      evidenceTriggers.current.get(pendingEvidenceFocus.current)?.focus()
      pendingEvidenceFocus.current = null
    }
  }, [evidenceId])

  const closeEvidence = () => {
    pendingEvidenceFocus.current = evidenceId
    setEvidenceId(null)
  }

  const handleEvidenceKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      closeEvidence()
      return
    }
    if (event.key !== 'Tab' || !evidenceDialog.current) return
    const focusable = Array.from(
      evidenceDialog.current.querySelectorAll<HTMLElement>('[tabindex="-1"], button:not(:disabled)'),
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

  const toggleSelected = (id: string) => {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const selectedCandidates = candidates.filter((candidate) => selected.has(candidate.id))

  return (
    <main className="review-layout" id="main-content">
      <section className="review-heading">
        <div>
          <p className="context-line">Subscription review</p>
          <h1>Sort what stays in your inbox.</h1>
          <p>Nothing is selected. Open any row to see why it was classified.</p>
        </div>
        <p className="selection-total" aria-live="polite">
          <strong>{selected.size}</strong> selected
        </p>
      </section>

      <div className="sorting-trays">
        {categories.map((category) => {
          const items = candidates.filter((candidate) => candidate.category === category.id)
          const selectedCount = items.filter((candidate) => selected.has(candidate.id)).length
          const regionId = `category-${category.id}`
          return (
            <section className={`category category--${category.id}`} key={category.id}>
              <button
                className="category__toggle"
                type="button"
                aria-expanded={expanded[category.id]}
                aria-controls={regionId}
                onClick={() =>
                  setExpanded((current) => ({ ...current, [category.id]: !current[category.id] }))
                }
              >
                <span className="category__symbol" aria-hidden="true">
                  {expanded[category.id] ? '−' : '+'}
                </span>
                <span className="category__name">{category.label}</span>
                <span className="category__note">{category.note}</span>
                <span className="category__counts">
                  {items.length} {items.length === 1 ? 'subscription' : 'subscriptions'} ·{' '}
                  {selectedCount} selected
                </span>
              </button>

              {expanded[category.id] && (
                <div id={regionId} role="region" aria-label={`${category.label} subscriptions`}>
                  {items.length === 0 ? (
                    <p className="category__empty">
                      {category.id === 'marketing'
                        ? 'No marketing subscriptions found in this scan.'
                        : 'No messages in this category.'}
                    </p>
                  ) : (
                    <ul className="candidate-list">
                      {items.map((candidate) => {
                        const name = senderName(candidate.sender)
                        return (
                          <li className="candidate" key={`${candidate.id}-${candidate.revision}`}>
                            <label className="candidate__select">
                              <input
                                type="checkbox"
                                checked={selected.has(candidate.id)}
                                onChange={() => toggleSelected(candidate.id)}
                                aria-label={`Select ${name}`}
                              />
                            </label>
                            <div className="candidate__identity">
                              <strong>{name}</strong>
                              <span>{candidate.representativeSubject}</span>
                            </div>
                            <div className="candidate__evidence">
                              <span>{candidate.reason}</span>
                              <button
                                className="text-button"
                                type="button"
                                ref={(node) => {
                                  if (node) evidenceTriggers.current.set(candidate.id, node)
                                  else evidenceTriggers.current.delete(candidate.id)
                                }}
                                onClick={() => setEvidenceId(candidate.id)}
                                aria-label={`View evidence for ${name}`}
                              >
                                View evidence
                              </button>
                            </div>
                            <div className="candidate__meta">
                              <span>
                                {candidate.messageCount}{' '}
                                {candidate.messageCount === 1 ? 'message' : 'messages'} ·{' '}
                                {candidate.dateRange}
                              </span>
                              <span>{methodLabels[candidate.method]} · {candidate.targetDisplay}</span>
                            </div>
                            <label className="candidate__correction">
                              <span className="visually-hidden">Correct category for {name}</span>
                              <select
                                aria-label={`Correct category for ${name}`}
                                value={candidate.category}
                                onChange={(event) => {
                                  setSelected((current) => {
                                    const next = new Set(current)
                                    next.delete(candidate.id)
                                    return next
                                  })
                                  onCorrect(
                                    candidate.id,
                                    candidate.revision,
                                    event.target.value as Category,
                                  )
                                }}
                              >
                                <option value="marketing">Marketing</option>
                                <option value="unclear">Unclear</option>
                                <option value="non_marketing">Non-marketing</option>
                              </select>
                            </label>
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </div>
              )}
            </section>
          )
        })}
      </div>

      <footer className="review-actions">
        <span>{selected.size ? 'Selections stay visible in category counts.' : 'Choose subscriptions to continue.'}</span>
        <button
          className="primary-action"
          type="button"
          disabled={selected.size === 0}
          onClick={() => onCreatePlan(selectedCandidates)}
        >
          {selected.size ? `Review ${selected.size} ${selected.size === 1 ? 'action' : 'actions'}` : 'Review actions'}
        </button>
      </footer>

      {evidence && (
        <div className="dialog-backdrop">
          <section
            ref={evidenceDialog}
            className="evidence-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="evidence-title"
            onKeyDown={handleEvidenceKeyDown}
          >
            <p className="context-line">{senderName(evidence.sender)}</p>
            <h2 id="evidence-title" ref={evidenceHeading} tabIndex={-1}>Classification evidence</h2>
            <blockquote>{evidence.evidenceQuote}</blockquote>
            <p>{evidence.reason}</p>
            <button className="secondary-action" type="button" onClick={closeEvidence}>
              Close evidence
            </button>
          </section>
        </div>
      )}
    </main>
  )
}
