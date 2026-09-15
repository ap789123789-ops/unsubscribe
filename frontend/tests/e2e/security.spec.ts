import { expect, test } from '@playwright/test'

test('@security rejects non-local hosts and mutations without a bound CSRF token', async ({ request }) => {
  const local = await request.get('/api/health')
  const hostileHost = await request.get('/api/health', { headers: { Host: 'attacker.example' } })
  const missingConsent = await request.post('/api/session/verify', {
    headers: { Origin: 'http://127.0.0.1:8000' },
  })

  expect(local.headers()['content-security-policy']).toContain("default-src 'self'")
  expect(local.headers()['x-content-type-options']).toBe('nosniff')
  expect(local.headers()['referrer-policy']).toBe('no-referrer')
  expect(hostileHost.status()).toBe(400)
  expect(missingConsent.status()).toBe(403)
})

test('@security renders sender-controlled text inert and never exposes signed targets', async ({ page }) => {
  await page.goto('/review')

  await expect(page.getByText('<img src=x onerror="window.__unsubscribeXss=1">')).toBeVisible()
  await expect(page.locator('img[src="x"]')).toHaveCount(0)
  await expect(page.getByText('private-fixture')).toHaveCount(0)
  expect(await page.evaluate(() => Reflect.get(window, '__unsubscribeXss'))).toBeUndefined()

  await page.getByRole('button', { name: 'View evidence for Hostile Fixture' }).click()
  await expect(page.getByText('<script>window.__unsubscribeXss=2</script>')).toBeVisible()
  await expect(page.locator('script')).toHaveCount(1)
  expect(await page.evaluate(() => Reflect.get(window, '__unsubscribeXss'))).toBeUndefined()
})
