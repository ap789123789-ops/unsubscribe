import createClient from 'openapi-fetch'

import type { components, paths } from './generated/schema'
import type { Category, ReviewCandidate } from '../features/review/ReviewPage'

export const api = createClient<paths>({ baseUrl: window.location.origin })

export async function getHealth() {
  const { data, error } = await api.GET('/api/health')
  if (error || !data) throw new Error('Backend health check failed')
  return data
}

let csrfToken: string | null = null

async function mutationHeaders() {
  if (!csrfToken) {
    const { data, error } = await api.GET('/api/session')
    if (error || !data) throw new Error('Local session could not be established')
    csrfToken = data.csrf_token
  }
  return { 'X-CSRF-Token': csrfToken }
}

export async function beginGoogleOAuth(
  intent: components['schemas']['OAuthIntent'] = 'read',
  returnTo = '/review',
) {
  const { data, error } = await api.POST('/auth/google/start', {
    headers: await mutationHeaders(),
    params: { query: { intent, return_to: returnTo } },
  })
  if (error || !data) throw new Error('Google OAuth could not start')
  return data
}

export async function getAccount() {
  const { data, error } = await api.GET('/api/account')
  if (error || !data) throw new Error('Gmail account status is unavailable')
  return data
}

export async function disconnectGoogle() {
  const { error } = await api.POST('/api/accounts/disconnect', {
    headers: await mutationHeaders(),
  })
  if (error) throw new Error('Gmail could not be disconnected')
}

export async function startScan(body: components['schemas']['ScanCreateRequest']) {
  const { data, error } = await api.POST('/api/scans', {
    headers: await mutationHeaders(),
    body,
  })
  if (error || !data) {
    const detail = (
      error as { detail?: { code?: string; message?: string } } | undefined
    )?.detail
    const failure = new Error(detail?.message ?? 'Scan failed. Check the local backend and retry.')
    failure.name = detail?.code ?? 'scan_failed'
    throw failure
  }
  return data
}

function shortDateRange(first: string, last: string) {
  const formatter = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' })
  return `${formatter.format(new Date(first))}–${formatter.format(new Date(last))}`
}

export async function listCandidates(): Promise<ReviewCandidate[]> {
  const { data, error } = await api.GET('/api/candidates')
  if (error || !data) throw new Error('Candidates could not be loaded')
  return data.items.map((candidate) => ({
    id: candidate.id,
    revision: candidate.revision,
    sender: candidate.sender,
    representativeSubject: candidate.representative_subject,
    messageCount: candidate.message_count,
    category: candidate.category,
    confidence: candidate.confidence,
    reason: candidate.reason,
    evidenceQuote: candidate.evidence_quote,
    method: candidate.method as ReviewCandidate['method'],
    targetDisplay: candidate.target_display,
    dateRange: shortDateRange(candidate.first_seen, candidate.last_seen),
  }))
}

export async function correctCandidate(
  candidateId: string,
  expectedRevision: number,
  category: Category,
) {
  const { data, error } = await api.PATCH('/api/candidates/{candidate_id}', {
    params: { path: { candidate_id: candidateId } },
    headers: await mutationHeaders(),
    body: { category, expected_revision: expectedRevision },
  })
  if (error || !data) throw new Error('Candidate correction was rejected')
  return data
}

export async function createActionPlan(
  selections: components['schemas']['SelectionRequest'][],
) {
  const { data, error } = await api.POST('/api/action-plans', {
    headers: await mutationHeaders(),
    body: { selections },
  })
  if (error || !data) throw new Error('Action plan could not be created')
  return data
}

export type ActionPlanView = components['schemas']['ActionPlanResponse']

export async function getActionPlan(planId: string): Promise<ActionPlanView> {
  const { data, error } = await api.GET('/api/action-plans/{plan_id}', {
    params: { path: { plan_id: planId } },
  })
  if (error || !data) throw new Error('Action plan could not be loaded')
  return data
}

export type ActionView = components['schemas']['ActionResponse']

export async function confirmActionPlan(
  planId: string,
  digest: string,
): Promise<ActionView[]> {
  const { data, error } = await api.POST('/api/action-plans/{plan_id}/confirm', {
    params: { path: { plan_id: planId } },
    headers: await mutationHeaders(),
    body: { digest },
  })
  if (error || !data) {
    const detail = (error as { detail?: { code?: string; message?: string } } | undefined)?.detail
    const failure = new Error(detail?.message ?? 'Action plan confirmation failed')
    failure.name = detail?.code ?? 'action_confirmation_failed'
    throw failure
  }
  return data.items
}

export async function listPlanActions(planId: string): Promise<ActionView[]> {
  const { data, error } = await api.GET('/api/action-plans/{plan_id}/actions', {
    params: { path: { plan_id: planId } },
  })
  if (error || !data) throw new Error('Action activity could not be loaded')
  return data.items
}

export type ActivityActionView = components['schemas']['ActivityActionResponse']

export async function listActions(planId?: string): Promise<ActivityActionView[]> {
  const { data, error } = await api.GET('/api/actions', {
    params: { query: { limit: 500, ...(planId ? { plan_id: planId } : {}) } },
  })
  if (error || !data) throw new Error('Action activity could not be loaded')
  return data.items
}

export async function retryAction(actionId: string): Promise<ActivityActionView> {
  const { data, error } = await api.POST('/api/actions/{action_id}/retry', {
    params: { path: { action_id: actionId } },
    headers: await mutationHeaders(),
  })
  if (error || !data) {
    const detail = (error as { detail?: { code?: string; message?: string } } | undefined)?.detail
    const failure = new Error(detail?.message ?? 'This action could not be retried')
    failure.name = detail?.code ?? 'action_retry_failed'
    throw failure
  }
  return data
}

export type BrowserSessionView = components['schemas']['BrowserSessionResponse']

export async function getBrowserSession(sessionId: string): Promise<BrowserSessionView> {
  const { data, error } = await api.GET('/api/browser-sessions/{browser_session_id}', {
    params: { path: { browser_session_id: sessionId } },
  })
  if (error || !data) throw new Error('Browser intervention is no longer available')
  return data
}

export async function takeOverBrowser(sessionId: string): Promise<BrowserSessionView> {
  const { data, error } = await api.POST(
    '/api/browser-sessions/{browser_session_id}/take-over',
    {
      params: { path: { browser_session_id: sessionId } },
      headers: await mutationHeaders(),
    },
  )
  if (error || !data) throw new Error('The guarded browser could not be shown')
  return data
}

export async function resumeBrowser(sessionId: string) {
  const { data, error } = await api.POST('/api/browser-sessions/{browser_session_id}/resume', {
    params: { path: { browser_session_id: sessionId } },
    headers: await mutationHeaders(),
  })
  if (error || !data) throw new Error('The guarded browser could not resume')
  return data
}

export async function cancelBrowser(sessionId: string) {
  const { data, error } = await api.POST('/api/browser-sessions/{browser_session_id}/cancel', {
    params: { path: { browser_session_id: sessionId } },
    headers: await mutationHeaders(),
  })
  if (error || !data) throw new Error('The guarded browser could not be stopped')
  return data
}
