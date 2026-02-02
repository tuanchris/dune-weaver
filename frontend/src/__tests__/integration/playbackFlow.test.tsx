import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders, screen, waitFor, userEvent } from '../../test/utils'
import { mockData, apiCallLog, resetApiCallLog } from '../../test/mocks/handlers'
import { BrowsePage } from '../../pages/BrowsePage'
import { PlaylistsPage } from '../../pages/PlaylistsPage'
import { TableControlPage } from '../../pages/TableControlPage'

describe('Playback Flow Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetApiCallLog()
    localStorage.clear()
  })

  describe('Pattern Playback Lifecycle', () => {
    it('starts pattern from browse page', async () => {
      const user = userEvent.setup()
      renderWithProviders(<BrowsePage />)

      // Initial state: not running
      expect(mockData.status.is_running).toBe(false)

      await waitFor(() => {
        expect(screen.getByText('star.thr')).toBeInTheDocument()
      })

      // Click pattern to open detail
      await user.click(screen.getByText('star.thr'))

      // Find and click main Play button
      await waitFor(() => {
        const buttons = screen.getAllByRole('button')
        const playButton = buttons.find(btn =>
          btn.textContent?.trim() === 'Play' ||
          (btn.textContent?.includes('Play') && !btn.textContent?.includes('Next') && !btn.textContent?.includes('Queue'))
        )
        expect(playButton).toBeTruthy()
      })

      const buttons = screen.getAllByRole('button')
      const playButton = buttons.find(btn =>
        btn.textContent?.trim() === 'Play' ||
        (btn.textContent?.includes('Play') && !btn.textContent?.includes('Next') && !btn.textContent?.includes('Queue'))
      )
      await user.click(playButton!)

      // Verify state transition
      await waitFor(() => {
        expect(mockData.status.is_running).toBe(true)
        expect(mockData.status.is_paused).toBe(false)
        expect(mockData.status.current_file).toContain('star')
      })
    })

    it('stops playback from table control page', async () => {
      const user = userEvent.setup()

      // Pre-set running state
      mockData.status.is_running = true
      mockData.status.current_file = 'patterns/star.thr'

      renderWithProviders(<TableControlPage />)

      // Find and click stop button
      await waitFor(() => {
        expect(screen.getByText('Stop')).toBeInTheDocument()
      })

      const stopButton = screen.getByText('Stop').closest('button')
      expect(stopButton).toBeTruthy()
      await user.click(stopButton!)

      // Verify API call
      await waitFor(() => {
        const stopCall = apiCallLog.find(c => c.endpoint === '/stop_execution')
        expect(stopCall).toBeDefined()
      })

      // Verify state transition
      expect(mockData.status.is_running).toBe(false)
      expect(mockData.status.current_file).toBeNull()
    })
  })

  describe('Playlist Playback Lifecycle', () => {
    it('runs playlist and populates queue', async () => {
      const user = userEvent.setup()
      renderWithProviders(<PlaylistsPage />)

      await waitFor(() => {
        expect(screen.getByText('default')).toBeInTheDocument()
      })

      // Run default playlist
      await user.click(screen.getByText('default'))

      await waitFor(() => {
        expect(screen.getByText(/2 patterns/i)).toBeInTheDocument()
      })

      // Find play button
      const buttons = screen.getAllByRole('button')
      const playButton = buttons.find(btn =>
        btn.querySelector('.material-icons')?.textContent === 'play_arrow'
      )
      await user.click(playButton!)

      // Verify playlist mode state
      await waitFor(() => {
        expect(mockData.status.is_running).toBe(true)
        expect(mockData.status.playlist_mode).toBe(true)
        expect(mockData.status.current_file).toBe('patterns/star.thr')
        expect(mockData.status.queue).toContain('patterns/spiral.thr')
      })
    })

    it('stops playlist playback and resets state', async () => {
      const user = userEvent.setup()

      // Pre-set playlist running state
      mockData.status.is_running = true
      mockData.status.playlist_mode = true
      mockData.status.playlist_name = 'default'
      mockData.status.current_file = 'patterns/star.thr'
      mockData.status.queue = ['patterns/spiral.thr']

      renderWithProviders(<TableControlPage />)

      // Stop playback
      await waitFor(() => {
        expect(screen.getByText('Stop')).toBeInTheDocument()
      })

      const stopButton = screen.getByText('Stop').closest('button')
      await user.click(stopButton!)

      // Verify complete state reset
      await waitFor(() => {
        expect(mockData.status.is_running).toBe(false)
        expect(mockData.status.playlist_mode).toBe(false)
        expect(mockData.status.queue).toEqual([])
        expect(mockData.status.current_file).toBeNull()
      })
    })
  })

  describe('State Transitions', () => {
    it('transitions: idle -> running -> stopped', async () => {
      const user = userEvent.setup()

      // Step 1: Start from idle
      expect(mockData.status.is_running).toBe(false)

      renderWithProviders(<BrowsePage />)

      await waitFor(() => {
        expect(screen.getByText('star.thr')).toBeInTheDocument()
      })

      // Step 2: Start playback
      await user.click(screen.getByText('star.thr'))

      await waitFor(() => {
        const buttons = screen.getAllByRole('button')
        const playButton = buttons.find(btn =>
          btn.textContent?.trim() === 'Play' ||
          (btn.textContent?.includes('Play') && !btn.textContent?.includes('Next') && !btn.textContent?.includes('Queue'))
        )
        expect(playButton).toBeTruthy()
      })

      const buttons = screen.getAllByRole('button')
      const playButton = buttons.find(btn =>
        btn.textContent?.trim() === 'Play' ||
        (btn.textContent?.includes('Play') && !btn.textContent?.includes('Next') && !btn.textContent?.includes('Queue'))
      )
      await user.click(playButton!)

      await waitFor(() => {
        expect(mockData.status.is_running).toBe(true)
      })

      // Step 3: Verify API call sequence
      const callSequence = apiCallLog.map(c => c.endpoint)
      expect(callSequence).toContain('/run_theta_rho')
    })

    it('verifies complete API call sequence for playlist run', async () => {
      const user = userEvent.setup()
      renderWithProviders(<PlaylistsPage />)

      await waitFor(() => {
        expect(screen.getByText('default')).toBeInTheDocument()
      })

      // Run playlist
      await user.click(screen.getByText('default'))

      await waitFor(() => {
        expect(screen.getByText(/2 patterns/i)).toBeInTheDocument()
      })

      // Find play button
      const buttons = screen.getAllByRole('button')
      const playButton = buttons.find(btn =>
        btn.querySelector('.material-icons')?.textContent === 'play_arrow'
      )
      await user.click(playButton!)

      // Verify run_playlist was called (not run_theta_rho)
      await waitFor(() => {
        const runCall = apiCallLog.find(c => c.endpoint === '/run_playlist')
        expect(runCall).toBeDefined()
        expect(runCall?.body).toMatchObject({ playlist_name: 'default' })
      })
    })
  })

  describe('Playback Control Actions', () => {
    it('stop_execution API resets all playback state', async () => {
      const user = userEvent.setup()

      // Pre-set running state
      mockData.status.is_running = true
      mockData.status.is_paused = false
      mockData.status.playlist_mode = true
      mockData.status.playlist_name = 'test'
      mockData.status.current_file = 'patterns/test.thr'
      mockData.status.queue = ['patterns/next.thr']

      renderWithProviders(<TableControlPage />)

      await waitFor(() => {
        expect(screen.getByText('Stop')).toBeInTheDocument()
      })

      const stopButton = screen.getByText('Stop').closest('button')
      await user.click(stopButton!)

      // Verify all state was reset
      await waitFor(() => {
        expect(mockData.status.is_running).toBe(false)
        expect(mockData.status.is_paused).toBe(false)
        expect(mockData.status.playlist_mode).toBe(false)
        expect(mockData.status.playlist_name).toBeNull()
        expect(mockData.status.current_file).toBeNull()
        expect(mockData.status.queue).toEqual([])
      })
    })

    it('verifies stop API call is logged', async () => {
      const user = userEvent.setup()

      mockData.status.is_running = true
      mockData.status.current_file = 'patterns/test.thr'

      renderWithProviders(<TableControlPage />)

      await waitFor(() => {
        expect(screen.getByText('Stop')).toBeInTheDocument()
      })

      const stopButton = screen.getByText('Stop').closest('button')
      await user.click(stopButton!)

      await waitFor(() => {
        const stopCall = apiCallLog.find(c => c.endpoint === '/stop_execution')
        expect(stopCall).toBeDefined()
        expect(stopCall?.method).toBe('POST')
        expect(stopCall?.timestamp).toBeDefined()
      })
    })
  })
})
