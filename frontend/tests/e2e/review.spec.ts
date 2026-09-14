import { expect, test } from '@playwright/test'

test('reviews a real candidate list and creates an immutable confirmation plan', async ({ page }) => {
  await page.goto('/review')

  const marketing = page.locator('[aria-controls="category-marketing"]')
  const unclear = page.locator('[aria-controls="category-unclear"]')
  await expect(marketing).toHaveAttribute('aria-expanded', 'true')
  await expect(unclear).toHaveAttribute('aria-expanded', 'false')
  await expect(page.getByText('private-fixture')).toHaveCount(0)

  await page.getByRole('checkbox', { name: 'Select Morning Brief' }).check()
  await marketing.click()
  await expect(marketing).toHaveAttribute('aria-expanded', 'false')
  await expect(marketing).toHaveAccessibleName(/1 selected/i)

  await page.getByRole('button', { name: 'Review 1 action' }).click()

  await expect(page).toHaveURL(/\/confirm\//)
  await expect(page.getByRole('heading', { name: 'Confirm each destination before anything is sent.' })).toBeVisible()
  await expect(page.getByText('example.com', { exact: true })).toBeVisible()
  await expect(page.getByText('private-fixture')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Confirm unsubscribe from 1 list' })).toBeEnabled()
})

test('shows an exact mailto preview before staged Gmail send consent', async ({ page }) => {
  await page.goto('/review')

  await page.getByRole('checkbox', { name: 'Select Mailing Club' }).check()
  await page.getByRole('button', { name: 'Review 1 action' }).click()

  await expect(page.getByRole('heading', { name: 'Unsubscribe email' })).toBeVisible()
  await expect(page.getByText('leave@example.net')).toBeVisible()
  await expect(page.getByText('Remove me')).toBeVisible()
  await expect(page.getByText('Please unsubscribe this address')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Authorize Gmail sending' })).toBeVisible()
})
