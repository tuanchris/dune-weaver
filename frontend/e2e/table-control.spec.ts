import { test, expect } from '@playwright/test'
import { setupApiMocks, resetMockStatus } from './mocks/api'

test.describe('Table Control E2E', () => {
  test.beforeEach(async ({ page }) => {
    resetMockStatus()
    await setupApiMocks(page)

    // Add route for send_home
    await page.route('**/send_home', async route => {
      await route.fulfill({ json: { success: true } })
    })
  })

  test('displays control page with buttons', async ({ page }) => {
    await page.goto('/table-control')

    // Should show control buttons
    await expect(page.getByRole('button', { name: /home/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /stop/i })).toBeVisible()
  })

  test('can trigger home action', async ({ page }) => {
    await page.goto('/table-control')

    // Find and click home button
    const homeButton = page.getByRole('button', { name: /home/i })
    await expect(homeButton).toBeVisible()

    // Click should not throw error
    await homeButton.click()

    // Button should still be visible (action completed)
    await expect(homeButton).toBeVisible()
  })

  test('navigation bar shows all pages', async ({ page }) => {
    await page.goto('/table-control')

    // All nav items should be visible
    await expect(page.getByRole('link', { name: /browse/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /playlists/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /control/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /led/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /settings/i })).toBeVisible()
  })
})
