import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test, vi } from 'vitest'

import { ReviewPage, type ReviewCandidate } from '../../src/features/review/ReviewPage'

const candidates: ReviewCandidate[] = [
  {
    id: 'marketing-1',
    revision: 1,
    sender: 'Morning Brief <brief@example.com>',
    representativeSubject: 'This week in product',
    messageCount: 4,
    category: 'marketing',
    confidence: 0.93,
    reason: 'Recurring editorial newsletter',
    evidenceQuote: 'This week in product',
    method: 'rfc8058',
    targetDisplay: 'example.com',
    dateRange: 'Sep 1–14',
  },
  {
    id: 'unclear-1',
    revision: 1,
    sender: 'Community <hello@community.example>',
    representativeSubject: 'September update',
    messageCount: 2,
    category: 'unclear',
    confidence: 0.52,
    reason: 'Mixed editorial and account content',
    evidenceQuote: 'September update',
    method: 'browser',
    targetDisplay: 'community.example',
    dateRange: 'Sep 4–12',
  },
]

test('starts unselected and keeps the selected count visible when collapsed', async () => {
  const user = userEvent.setup()
  render(<ReviewPage candidates={candidates} onCreatePlan={vi.fn()} onCorrect={vi.fn()} />)

  expect(screen.getAllByRole('checkbox')).toHaveLength(1)
  expect(
    screen.getByRole('button', { name: /unclear.*0 selected/i }).getAttribute('aria-expanded'),
  ).toBe('false')

  await user.click(screen.getByRole('checkbox', { name: /morning brief/i }))
  await user.click(screen.getByRole('button', { name: /marketing.*1 selected/i }))

  expect(
    screen.getByRole('button', { name: /^marketing\b.*1 selected/i }).getAttribute('aria-expanded'),
  ).toBe('false')
  expect((screen.getByRole('button', { name: 'Review 1 action' }) as HTMLButtonElement).disabled).toBe(
    false,
  )
})

test('evidence dialog returns focus to its trigger', async () => {
  const user = userEvent.setup()
  render(<ReviewPage candidates={candidates} onCreatePlan={vi.fn()} onCorrect={vi.fn()} />)
  const trigger = screen.getByRole('button', { name: /view evidence for morning brief/i })

  await user.click(trigger)
  const dialog = screen.getByRole('dialog', { name: /classification evidence/i })
  expect(within(dialog).getByText('This week in product').textContent).toBe('This week in product')
  await user.click(within(dialog).getByRole('button', { name: 'Close evidence' }))

  expect(document.activeElement).toBe(trigger)
})

test('correcting a selected candidate clears its stale selection', async () => {
  const user = userEvent.setup()
  const onCorrect = vi.fn()
  render(<ReviewPage candidates={candidates} onCreatePlan={vi.fn()} onCorrect={onCorrect} />)

  await user.click(screen.getByRole('checkbox', { name: /morning brief/i }))
  await user.selectOptions(screen.getByLabelText(/correct category for morning brief/i), 'unclear')

  expect(onCorrect).toHaveBeenCalledWith('marketing-1', 1, 'unclear')
  expect((screen.getByRole('button', { name: 'Review actions' }) as HTMLButtonElement).disabled).toBe(
    true,
  )
})
