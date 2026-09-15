import { expect, test } from '@playwright/test'

test('@activity runs controlled one-click, email, and browser samples through the activity center', async ({ page }, testInfo) => {
  const sample = testInfo.repeatEachIndex + 1
  await page.goto('/review')

  await page.getByRole('checkbox', { name: `Select Dispatch Lab ${sample}` }).check()
  await page.getByRole('checkbox', { name: `Select Member Post ${sample}` }).check()
  await page.getByRole('checkbox', { name: `Select Product Circle ${sample}` }).check()
  await page.getByRole('button', { name: 'Review 3 actions' }).click()

  await expect(page.getByRole('heading', { name: 'One-click web request' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Unsubscribe email' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Website' })).toBeVisible()
  await expect(page.getByText('private-fixture')).toHaveCount(0)

  await page.getByRole('button', { name: 'Confirm unsubscribe from 3 lists' }).click()
  await page.getByRole('link', { name: 'View activity' }).click()

  const oneClick = page.getByRole('listitem', { name: `Dispatch Lab ${sample}: Request sent` })
  const email = page.getByRole('listitem', { name: `Member Post ${sample}: Request sent` })
  const browser = page.getByRole('listitem', { name: `Product Circle ${sample}: Your help is needed` })
  await expect(oneClick).toContainText('list processing is not verified')
  await expect(email).toContainText('Gmail accepted the unsubscribe email')
  await expect(browser).toContainText('Sign in to the sender')

  await browser.getByRole('button', { name: 'Review browser blocker' }).click()
  const dialog = page.getByRole('dialog', { name: 'Your help is needed' })
  await dialog.getByRole('button', { name: 'Take over in browser' }).click()
  await dialog.getByRole('button', { name: 'Resume automation' }).click()

  await expect(page.getByRole('listitem', { name: `Product Circle ${sample}: Unsubscribe confirmed` })).toBeVisible()
  await page.getByRole('link', { name: 'Activity' }).click()
  await expect(page).toHaveURL(/\/activity$/)
  await expect(page.getByRole('listitem', { name: `Dispatch Lab ${sample}: Request sent` })).toBeVisible()
  await expect(page.getByRole('listitem', { name: `Member Post ${sample}: Request sent` })).toBeVisible()
  await expect(page.getByRole('listitem', { name: `Product Circle ${sample}: Unsubscribe confirmed` })).toBeVisible()
  await expect(page.getByText('private-fixture')).toHaveCount(0)
})
