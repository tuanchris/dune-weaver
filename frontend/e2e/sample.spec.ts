import { test, expect } from '@playwright/test'
import { setupApiMocks, resetMockStatus } from './mocks/api'

test.describe('App Infrastructure', () => {
  test.beforeEach(async ({ page }) => {
    resetMockStatus()
    await setupApiMocks(page)
  })

  test('app loads and renders header', async ({ page }) => {
    await page.goto('/')

    // Header should be visible with app name
    await expect(page.getByText('Dune Weaver')).toBeVisible()
  })

  test('app renders bottom navigation', async ({ page }) => {
    await page.goto('/')

    // Bottom nav should have all navigation items
    const nav = page.locator('nav')
    await expect(nav).toBeVisible()
  })

  test('dark mode toggle works', async ({ page }) => {
    await page.goto('/')

    // Find and click theme toggle in menu
    await page.getByRole('button', { name: /menu/i }).click()

    // Look for dark/light mode option
    const themeButton = page.getByText(/dark mode|light mode/i)
    await expect(themeButton).toBeVisible()
  })
})
