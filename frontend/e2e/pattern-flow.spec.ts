import { test, expect } from '@playwright/test'
import { setupApiMocks, resetMockStatus, getMockStatus } from './mocks/api'

test.describe('Pattern Flow E2E', () => {
  test.beforeEach(async ({ page }) => {
    resetMockStatus()
    await setupApiMocks(page)
  })

  test('displays pattern list on browse page', async ({ page }) => {
    await page.goto('/')

    // Wait for patterns to load
    await expect(page.getByText('star.thr')).toBeVisible()
    await expect(page.getByText('spiral.thr')).toBeVisible()
    await expect(page.getByText('wave.thr')).toBeVisible()
  })

  test('can select pattern to view details', async ({ page }) => {
    await page.goto('/')

    // Wait for patterns to load
    await expect(page.getByText('star.thr')).toBeVisible()

    // Click on pattern
    await page.getByText('star.thr').click()

    // Detail panel should open (Sheet component)
    // The sheet contains a "Play" button with exact text (not "Play Next")
    await expect(page.getByRole('button', { name: 'play_arrow Play' })).toBeVisible({ timeout: 5000 })
  })

  test('can run pattern and UI shows running state', async ({ page }) => {
    await page.goto('/')

    // Wait for patterns
    await expect(page.getByText('star.thr')).toBeVisible()

    // Click pattern to open detail
    await page.getByText('star.thr').click()

    // Wait for detail panel
    await page.waitForTimeout(500)

    // Find and click run button
    const runButton = page.getByRole('button', { name: /run|play/i }).first()
    await expect(runButton).toBeVisible()
    await runButton.click()

    // Verify API was called and status updated
    await page.waitForTimeout(500)
    const status = getMockStatus()
    expect(status.is_running).toBe(true)
    expect(status.current_file).toContain('star')
  })

  test('search filters patterns correctly', async ({ page }) => {
    await page.goto('/')

    // Wait for patterns
    await expect(page.getByText('star.thr')).toBeVisible()
    await expect(page.getByText('spiral.thr')).toBeVisible()

    // Type in search
    const searchInput = page.getByPlaceholder(/search/i)
    await searchInput.fill('spiral')

    // Only spiral should be visible
    await expect(page.getByText('spiral.thr')).toBeVisible()
    await expect(page.getByText('star.thr')).not.toBeVisible()
  })
})
