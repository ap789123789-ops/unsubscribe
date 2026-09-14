import { expect, test } from '@playwright/test'

test('shows the production shell connected to FastAPI', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Connect your inbox to begin sorting.' })).toBeVisible()
  await expect(page.getByRole('status')).toHaveText('Backend ready')
})
