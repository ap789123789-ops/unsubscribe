import { expect, test } from '@playwright/test'

test('shows the production shell connected to FastAPI', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Clear the mail you no longer want.' })).toBeVisible()
  await expect(page.getByRole('status')).toHaveText('Backend ready')
})

