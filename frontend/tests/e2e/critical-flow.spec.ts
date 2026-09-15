import { expect, test } from '@playwright/test'

test('@critical confirms a reviewed one-click action and preserves honest status', async ({ page }) => {
  await page.goto('/review')
  await page.getByRole('checkbox', { name: 'Select Morning Brief' }).check()
  await page.getByRole('button', { name: 'Review 1 action' }).click()

  await expect(page.getByText('example.com', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Confirm unsubscribe from 1 list' }).click()
  await page.getByRole('link', { name: 'View activity' }).click()

  const action = page.getByRole('listitem').filter({ hasText: 'Request sent' })
  await expect(action).toBeVisible()
  await expect(action).toContainText('sender processing was not explicitly confirmed')
  await expect(page.getByRole('heading', { name: 'Unsubscribe confirmed' })).toHaveCount(0)
})
