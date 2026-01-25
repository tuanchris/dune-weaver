import { test, expect } from '@playwright/test'
import { setupApiMocks, resetMockStatus, getMockStatus } from './mocks/api'

test.describe('Playlist Flow E2E', () => {
  test.beforeEach(async ({ page }) => {
    resetMockStatus()
    await setupApiMocks(page)
  })

  test('navigates to playlists page and displays playlists', async ({ page }) => {
    await page.goto('/playlists')

    // Wait for playlists to load
    await expect(page.getByText('default')).toBeVisible()
    await expect(page.getByText('favorites')).toBeVisible()
  })

  test('can select and run a playlist', async ({ page }) => {
    await page.goto('/playlists')

    // Wait for playlists
    await expect(page.getByText('default')).toBeVisible()

    // Click playlist to select
    await page.getByText('default').click()

    // Wait for the playlist patterns to load
    // The Play button should become enabled once patterns are loaded
    await page.waitForTimeout(1000)

    // Find and click run button by its title attribute
    const runButton = page.locator('button[title="Run Playlist"]')
    await expect(runButton).toBeVisible({ timeout: 5000 })
    await runButton.click()

    // Verify playlist is running
    await page.waitForTimeout(500)
    const status = getMockStatus()
    expect(status.is_running).toBe(true)
    expect(status.playlist_mode).toBe(true)
    expect(status.playlist_name).toBe('default')
  })

  test('can navigate between browse and playlists', async ({ page }) => {
    // Start on browse
    await page.goto('/')
    await expect(page.getByText('star.thr')).toBeVisible()

    // Navigate to playlists via nav
    await page.getByRole('link', { name: /playlists/i }).click()
    await expect(page.getByText('default')).toBeVisible()

    // Navigate back to browse
    await page.getByRole('link', { name: /browse/i }).click()
    await expect(page.getByText('star.thr')).toBeVisible()
  })
})
