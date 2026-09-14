import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { correctCandidate, createActionPlan, listCandidates } from '../../api/client'
import { ReviewPage, type Category, type ReviewCandidate } from './ReviewPage'

export function ReviewRoute() {
  const [candidates, setCandidates] = useState<ReviewCandidate[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  const load = async () => {
    try {
      setCandidates(await listCandidates())
    } catch {
      setError('Candidates could not be loaded. Check that the local backend is running.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  if (loading) return <main className="page" id="main-content"><p role="status">Loading subscriptions…</p></main>
  if (error) return <main className="page" id="main-content"><p role="alert">{error}</p></main>

  return (
    <ReviewPage
      candidates={candidates}
      onCorrect={async (id, revision, category: Category) => {
        await correctCandidate(id, revision, category)
        await load()
      }}
      onCreatePlan={async (selected) => {
        const plan = await createActionPlan(selected.map(({ id, revision }) => ({ candidate_id: id, revision })))
        navigate(`/confirm/${plan.id}`)
      }}
    />
  )
}

