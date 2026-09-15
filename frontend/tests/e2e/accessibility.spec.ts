import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

async function expectNoSeriousAxeViolations(page: Parameters<typeof AxeBuilder>[0]['page']) {
  const results = await new AxeBuilder({ page }).analyze()
  const blocking = results.violations.filter(({ impact }) => (
    impact === 'serious' || impact === 'critical'
  ))
  expect(blocking).toEqual([])
}

test('@accessibility review and intervention have no serious axe violations', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce', forcedColors: 'active' })
  await page.goto('/review')
  await expect(page.getByRole('heading', { name: 'Sort what stays in your inbox.' })).toBeVisible()
  await expectNoSeriousAxeViolations(page)

  await page.locator('[aria-controls="category-unclear"]').click()
  await page.getByRole('checkbox', { name: 'Select Design Forum' }).check()
  await page.getByRole('button', { name: 'Review 1 action' }).click()
  await page.getByRole('button', { name: 'Confirm unsubscribe from 1 list' }).click()
  await page.getByRole('link', { name: 'View activity' }).click()
  await page.getByRole('button', { name: 'Review browser blocker' }).click()

  const dialog = page.getByRole('dialog', { name: 'Your help is needed' })
  const heading = dialog.getByRole('heading', { name: 'Your help is needed' })
  await expect(heading).toBeFocused()
  await expectNoSeriousAxeViolations(page)

  await page.keyboard.press('Shift+Tab')
  await expect(dialog.getByRole('button', { name: 'Close' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('listitem').filter({ hasText: 'Your help is needed' })).toBeFocused()
})
