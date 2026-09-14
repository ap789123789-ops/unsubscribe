import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'

import { ConfirmationPage } from '../../src/features/confirmation/ConfirmationPage'

const api = vi.hoisted(() => ({
  beginGoogleOAuth: vi.fn(),
  confirmActionPlan: vi.fn(),
  getAccount: vi.fn(),
  getActionPlan: vi.fn(),
}))

vi.mock('../../src/api/client', () => api)

const baseItem = {
  candidate_id: 'candidate-1',
  revision: 1,
  sender: 'Brief <brief@example.com>',
  subject: 'Weekly brief',
  target_display: 'example.com',
}

function renderConfirmation() {
  render(
    <MemoryRouter initialEntries={['/confirm/plan-1']}>
      <Routes>
        <Route path="confirm/:planId" element={<ConfirmationPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

test('shows the exact mailto recipient, subject, and body before requesting send consent', async () => {
  api.getActionPlan.mockResolvedValue({
    id: 'plan-1',
    digest: 'd'.repeat(64),
    confirmed: false,
    items: [{
      ...baseItem,
      method: 'mailto',
      target_display: 'leave@example.com',
      mail_preview: {
        recipient: 'leave@example.com',
        subject: 'Remove me',
        body: 'Please unsubscribe me',
      },
    }],
  })
  api.getAccount.mockResolvedValue({ connected: true, scopes: ['gmail.readonly'] })

  renderConfirmation()

  await screen.findByRole('heading', { name: 'Unsubscribe email' })
  expect(screen.getByText('leave@example.com').textContent).toBe('leave@example.com')
  expect(screen.getByText('Remove me').textContent).toBe('Remove me')
  expect(screen.getByText('Please unsubscribe me').textContent).toBe('Please unsubscribe me')
  expect(screen.getByRole('button', { name: 'Authorize Gmail sending' })).toBeTruthy()
})

test('confirms an RFC plan once and reports submitted without claiming completion', async () => {
  const user = userEvent.setup()
  api.getActionPlan.mockResolvedValue({
    id: 'plan-1',
    digest: 'd'.repeat(64),
    confirmed: false,
    items: [{ ...baseItem, method: 'rfc8058', mail_preview: null }],
  })
  api.confirmActionPlan.mockResolvedValue([
    { id: 'action-1', candidate_id: 'candidate-1', method: 'rfc8058', state: 'submitted' },
  ])
  renderConfirmation()

  await user.click(await screen.findByRole('button', { name: 'Confirm unsubscribe from 1 list' }))

  expect(api.confirmActionPlan).toHaveBeenCalledWith('plan-1', 'd'.repeat(64))
  expect(await screen.findByText('Submitted — list processing is not verified')).toBeTruthy()
})
