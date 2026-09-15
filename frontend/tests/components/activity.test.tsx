import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'

import { ActivityPage } from '../../src/features/activity/ActivityPage'

const api = vi.hoisted(() => ({
  beginGoogleOAuth: vi.fn(),
  cancelBrowser: vi.fn(),
  getAccount: vi.fn(),
  getBrowserSession: vi.fn(),
  listActions: vi.fn(),
  listPlanActions: vi.fn(),
  resumeBrowser: vi.fn(),
  retryAction: vi.fn(),
  takeOverBrowser: vi.fn(),
}))

vi.mock('../../src/api/client', () => api)

const activity = [
  {
    id: 'rfc-submitted',
    plan_id: 'plan-1',
    candidate_id: 'candidate-1',
    sender: 'Morning Brief <brief@example.com>',
    subject: 'Monday edition',
    target_display: 'example.com',
    method: 'rfc8058',
    state: 'submitted',
    evidence_code: 'rfc8058_request_accepted',
    safe_detail: 'The one-click request was accepted; list processing is not verified.',
    updated_at: '2026-09-14T12:00:00Z',
    retry_available: false,
    browser_session_id: null,
  },
  {
    id: 'browser-blocked',
    plan_id: 'plan-1',
    candidate_id: 'candidate-2',
    sender: 'Community <hello@community.example>',
    subject: 'September update',
    target_display: 'community.example',
    method: 'browser',
    state: 'needs_user',
    evidence_code: 'login_required',
    safe_detail: 'Sign in to the sender site, then resume automation.',
    updated_at: '2026-09-14T12:01:00Z',
    retry_available: false,
    browser_session_id: 'browser-session-1',
  },
  {
    id: 'rfc-retry',
    plan_id: 'plan-2',
    candidate_id: 'candidate-3',
    sender: 'Product Notes <notes@example.org>',
    subject: 'Weekly release notes',
    target_display: 'example.org',
    method: 'rfc8058',
    state: 'failed',
    evidence_code: 'http_503',
    safe_detail: 'The server rejected the request. A reviewed retry may be available.',
    updated_at: '2026-09-14T12:02:00Z',
    retry_available: true,
    browser_session_id: null,
  },
  {
    id: 'mailto-auth',
    plan_id: 'plan-2',
    candidate_id: 'candidate-4',
    sender: 'Mailing Club <club@example.net>',
    subject: 'Club dispatch',
    target_display: 'leave@example.net',
    method: 'mailto',
    state: 'needs_user',
    evidence_code: 'gmail_send_authorization_required',
    safe_detail: 'Gmail send permission is no longer available.',
    updated_at: '2026-09-14T12:03:00Z',
    retry_available: true,
    browser_session_id: null,
  },
]

function renderActivity(path = '/activity') {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="activity" element={<ActivityPage />} />
        <Route path="activity/:planId" element={<ActivityPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.listActions.mockResolvedValue(activity)
  api.getAccount.mockResolvedValue({ connected: true, scopes: ['gmail.readonly'] })
})

test('shows a filterable global ledger with only policy-eligible repair controls', async () => {
  const user = userEvent.setup()
  renderActivity()

  const morning = await screen.findByRole('listitem', { name: /Morning Brief/i })
  expect(within(morning).getByText('Request sent')).toBeTruthy()
  expect(within(morning).getByText(/list processing is not verified/i)).toBeTruthy()
  expect(within(morning).queryByRole('button')).toBeNull()

  const community = screen.getByRole('listitem', { name: /Community/i })
  expect(within(community).getByRole('button', { name: 'Review browser blocker' })).toBeTruthy()
  const retryable = screen.getByRole('listitem', { name: /Product Notes/i })
  expect(within(retryable).getByRole('button', { name: 'Review one-click retry' })).toBeTruthy()
  const mailto = screen.getByRole('listitem', { name: /Mailing Club/i })
  expect(within(mailto).getByRole('button', { name: 'Reconnect Gmail' })).toBeTruthy()

  await user.click(screen.getByRole('button', { name: /Needs attention 3/i }))

  expect(screen.queryByRole('listitem', { name: /Morning Brief/i })).toBeNull()
  expect(screen.getByRole('listitem', { name: /Community/i })).toBeTruthy()
  expect(screen.getByRole('listitem', { name: /Product Notes/i })).toBeTruthy()
  expect(screen.getByRole('listitem', { name: /Mailing Club/i })).toBeTruthy()
})

test('requires a second confirmation before the one allowed one-click retry', async () => {
  const user = userEvent.setup()
  api.listActions.mockResolvedValue([activity[2]])
  api.retryAction.mockResolvedValue({
    ...activity[2],
    state: 'submitted',
    evidence_code: 'rfc8058_request_accepted',
    safe_detail: 'The one-click request was accepted; list processing is not verified.',
    retry_available: false,
  })
  renderActivity()

  await user.click(await screen.findByRole('button', { name: 'Review one-click retry' }))

  const dialog = screen.getByRole('dialog', { name: 'Retry the one-click request?' })
  expect(within(dialog).getByText(/one allowed retry/i)).toBeTruthy()
  expect(within(dialog).getByText(/uncertain submission is never retried/i)).toBeTruthy()

  await user.click(within(dialog).getByRole('button', { name: 'Retry one-click request' }))

  expect(api.retryAction).toHaveBeenCalledWith('rfc-retry')
  const updated = screen.getByRole('listitem', { name: /Product Notes: Request sent/i })
  expect(within(updated).getByText(/list processing is not verified/i)).toBeTruthy()
  expect(within(updated).queryByRole('button')).toBeNull()
})
