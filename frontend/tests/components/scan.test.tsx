import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test, vi } from 'vitest'

import { ScanPage } from '../../src/features/scan/ScanPage'

const api = vi.hoisted(() => ({
  startScan: vi.fn(),
}))

vi.mock('../../src/api/client', () => api)

beforeEach(() => {
  vi.clearAllMocks()
})

test('shows the safe backend reason when message processing fails', async () => {
  const user = userEvent.setup()
  api.startScan.mockRejectedValue(
    new Error('One email could not be processed. Progress was saved; retry the scan.'),
  )
  render(
    <MemoryRouter>
      <ScanPage />
    </MemoryRouter>,
  )

  await user.click(screen.getByRole('button', { name: 'Scan email' }))

  expect(
    await screen.findByText('One email could not be processed. Progress was saved; retry the scan.'),
  ).toBeTruthy()
  expect(screen.queryByText(/connect or reconnect gmail/i)).toBeNull()
})

test('reuses the scan id when the user retries the same bounded scan', async () => {
  const user = userEvent.setup()
  api.startScan
    .mockRejectedValueOnce(
      new Error('One email could not be processed. Progress was saved; retry the scan.'),
    )
    .mockResolvedValueOnce({ processed_count: 2, completed: true })
  render(
    <MemoryRouter>
      <ScanPage />
    </MemoryRouter>,
  )

  const button = screen.getByRole('button', { name: 'Scan email' })
  await user.click(button)
  await screen.findByText(/progress was saved/i)
  await user.click(button)
  await screen.findByText(/read 2 messages/i)

  const firstRequest = api.startScan.mock.calls[0][0]
  const retryRequest = api.startScan.mock.calls[1][0]
  expect(retryRequest.scan_id).toBe(firstRequest.scan_id)
})

test('prevents a second scan submission while one is pending', async () => {
  const user = userEvent.setup()
  let finishScan: ((value: { processed_count: number; completed: boolean }) => void) | undefined
  api.startScan.mockImplementation(
    () =>
      new Promise((resolve) => {
        finishScan = resolve
      }),
  )
  render(
    <MemoryRouter>
      <ScanPage />
    </MemoryRouter>,
  )

  const button = screen.getByRole('button', { name: 'Scan email' })
  await user.click(button)

  expect(button.hasAttribute('disabled')).toBe(true)
  await user.click(button)
  expect(api.startScan).toHaveBeenCalledTimes(1)

  finishScan?.({ processed_count: 1, completed: true })
  expect(await screen.findByText(/read 1 messages/i)).toBeTruthy()
  expect(button.hasAttribute('disabled')).toBe(false)
})
