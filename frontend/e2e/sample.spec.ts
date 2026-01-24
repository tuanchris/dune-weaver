import { test, expect } from '@playwright/test'

test.describe('Test Infrastructure', () => {
  test('app loads successfully', async ({ page }) => {
    await page.goto('/')
    // App should render without crashing
    await expect(page.locator('body')).toBeVisible()
  })
})
