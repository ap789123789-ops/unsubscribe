import { expect, test } from '@playwright/test'

test('@browser pauses for user takeover and resumes without a second automatic click', async ({ page }) => {
  await page.goto('/review')
  await page.locator('[aria-controls="category-unclear"]').click()
  await page.getByRole('checkbox', { name: 'Select Community' }).check()
  await page.getByRole('button', { name: 'Review 1 action' }).click()
  await page.getByRole('button', { name: 'Confirm unsubscribe from 1 list' }).click()
  await page.getByRole('link', { name: 'View activity' }).click()

  await page.getByRole('button', { name: 'Review browser blocker' }).click()
  const dialog = page.getByRole('dialog', { name: 'Your help is needed' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('heading', { name: 'Your help is needed' })).toBeFocused()
  await expect(dialog.getByText('https://community.example')).toBeVisible()
  await expect(dialog.getByText('Not issued')).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Take over in browser' })).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Resume automation' })).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Stop this action' })).toBeVisible()

  await dialog.getByRole('button', { name: 'Take over in browser' }).click()
  await dialog.getByRole('button', { name: 'Resume automation' }).click()

  await expect(dialog).toBeHidden()
  const completedRow = page.getByRole('listitem').filter({ hasText: 'Unsubscribe confirmed' })
  await expect(completedRow).toBeVisible()
  await expect(completedRow).toBeFocused()
})
