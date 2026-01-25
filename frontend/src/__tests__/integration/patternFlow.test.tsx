import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders, screen, waitFor, userEvent } from '../../test/utils'
import { mockData, apiCallLog, resetApiCallLog } from '../../test/mocks/handlers'
import { BrowsePage } from '../../pages/BrowsePage'

describe('Pattern Flow Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetApiCallLog()
  })

  describe('Browse -> Select -> Run Flow', () => {
    it('displays pattern list from API', async () => {
      renderWithProviders(<BrowsePage />)

      await waitFor(() => {
        expect(screen.getByText('star.thr')).toBeInTheDocument()
        expect(screen.getByText('spiral.thr')).toBeInTheDocument()
      })
    })

    it('opens pattern detail when clicking pattern card', async () => {
      const user = userEvent.setup()
      renderWithProviders(<BrowsePage />)

      await waitFor(() => {
        expect(screen.getByText('star.thr')).toBeInTheDocument()
      })

      // Click on pattern card
      await user.click(screen.getByText('star.thr'))

      // Detail sheet should open - pattern name appears twice (grid + sheet title)
      await waitFor(() => {
        const patternNames = screen.getAllByText('star.thr')
        expect(patternNames.length).toBeGreaterThan(1)
      })
    })

    it('runs pattern and verifies API call with correct file', async () => {
      const user = userEvent.setup()
      renderWithProviders(<BrowsePage />)

      // Wait for patterns to load
      await waitFor(() => {
        expect(screen.getByText('star.thr')).toBeInTheDocument()
      })

      // Pre-condition: not running
      expect(mockData.status.is_running).toBe(false)

      // Click pattern to open detail sheet
      await user.click(screen.getByText('star.thr'))

      // Wait for sheet to open and find the main Play button (lg size, not the smaller ones)
      await waitFor(() => {
        // The main Play button has "Play" text and play_arrow icon
        const buttons = screen.getAllByRole('button')
        const playButton = buttons.find(btn =>
          btn.textContent?.trim() === 'Play' ||
          (btn.textContent?.includes('Play') && !btn.textContent?.includes('Next') && !btn.textContent?.includes('Queue'))
        )
        expect(playButton).toBeTruthy()
      })

      // Click the main Play button
      const buttons = screen.getAllByRole('button')
      const playButton = buttons.find(btn =>
        btn.textContent?.trim() === 'Play' ||
        (btn.textContent?.includes('Play') && !btn.textContent?.includes('Next') && !btn.textContent?.includes('Queue'))
      )
      await user.click(playButton!)

      // Verify API was called with correct file
      await waitFor(() => {
        const runCall = apiCallLog.find(c => c.endpoint === '/run_theta_rho')
        expect(runCall).toBeDefined()
        expect(runCall?.body).toMatchObject({
          file_name: expect.stringContaining('star')
        })
      })

      // Verify mock state was updated
      expect(mockData.status.is_running).toBe(true)
      expect(mockData.status.current_file).toContain('star')
    })

    it('updates mock state after pattern starts running', async () => {
      const user = userEvent.setup()
      renderWithProviders(<BrowsePage />)

      await waitFor(() => {
        expect(screen.getByText('star.thr')).toBeInTheDocument()
      })

      // Pre-condition: not running
      expect(mockData.status.is_running).toBe(false)

      // Click pattern to open detail
      await user.click(screen.getByText('star.thr'))

      // Wait for sheet to open and find main Play button
      await waitFor(() => {
        const buttons = screen.getAllByRole('button')
        const playButton = buttons.find(btn =>
          btn.textContent?.trim() === 'Play' ||
          (btn.textContent?.includes('Play') && !btn.textContent?.includes('Next') && !btn.textContent?.includes('Queue'))
        )
        expect(playButton).toBeTruthy()
      })

      // Click the main Play button
      const buttons = screen.getAllByRole('button')
      const playButton = buttons.find(btn =>
        btn.textContent?.trim() === 'Play' ||
        (btn.textContent?.includes('Play') && !btn.textContent?.includes('Next') && !btn.textContent?.includes('Queue'))
      )
      await user.click(playButton!)

      // Post-condition: running
      await waitFor(() => {
        expect(mockData.status.is_running).toBe(true)
      })
    })
  })

  describe('Search -> Filter -> Run Flow', () => {
    it('filters patterns by search then runs filtered result', async () => {
      const user = userEvent.setup()
      renderWithProviders(<BrowsePage />)

      await waitFor(() => {
        expect(screen.getByText('star.thr')).toBeInTheDocument()
        expect(screen.getByText('spiral.thr')).toBeInTheDocument()
      })

      // Search for "spiral"
      const searchInput = screen.getByPlaceholderText(/search/i)
      await user.type(searchInput, 'spiral')

      // Only spiral should be visible
      await waitFor(() => {
        expect(screen.getByText('spiral.thr')).toBeInTheDocument()
        expect(screen.queryByText('star.thr')).not.toBeInTheDocument()
      })

      // Click and run the filtered pattern
      await user.click(screen.getByText('spiral.thr'))

      // Wait for sheet and find main Play button
      await waitFor(() => {
        const buttons = screen.getAllByRole('button')
        const playButton = buttons.find(btn =>
          btn.textContent?.trim() === 'Play' ||
          (btn.textContent?.includes('Play') && !btn.textContent?.includes('Next') && !btn.textContent?.includes('Queue'))
        )
        expect(playButton).toBeTruthy()
      })

      // Click main Play button
      const buttons = screen.getAllByRole('button')
      const playButton = buttons.find(btn =>
        btn.textContent?.trim() === 'Play' ||
        (btn.textContent?.includes('Play') && !btn.textContent?.includes('Next') && !btn.textContent?.includes('Queue'))
      )
      await user.click(playButton!)

      // Verify correct pattern was run
      await waitFor(() => {
        const runCall = apiCallLog.find(c => c.endpoint === '/run_theta_rho')
        expect(runCall?.body).toMatchObject({
          file_name: expect.stringContaining('spiral')
        })
      })
    })
  })

  describe('API Call Verification', () => {
    it('logs API call with timestamp and method', async () => {
      const user = userEvent.setup()
      renderWithProviders(<BrowsePage />)

      await waitFor(() => {
        expect(screen.getByText('star.thr')).toBeInTheDocument()
      })

      // Run a pattern
      await user.click(screen.getByText('star.thr'))

      // Wait for sheet and find main Play button
      await waitFor(() => {
        const buttons = screen.getAllByRole('button')
        const playButton = buttons.find(btn =>
          btn.textContent?.trim() === 'Play' ||
          (btn.textContent?.includes('Play') && !btn.textContent?.includes('Next') && !btn.textContent?.includes('Queue'))
        )
        expect(playButton).toBeTruthy()
      })

      // Click main Play button
      const allButtons = screen.getAllByRole('button')
      const mainPlayButton = allButtons.find(btn =>
        btn.textContent?.trim() === 'Play' ||
        (btn.textContent?.includes('Play') && !btn.textContent?.includes('Next') && !btn.textContent?.includes('Queue'))
      )
      await user.click(mainPlayButton!)

      // Verify API call log structure
      await waitFor(() => {
        const runCall = apiCallLog.find(c => c.endpoint === '/run_theta_rho')
        expect(runCall).toBeDefined()
        expect(runCall?.method).toBe('POST')
        expect(runCall?.timestamp).toBeDefined()
        expect(typeof runCall?.timestamp).toBe('number')
      })
    })
  })
})
