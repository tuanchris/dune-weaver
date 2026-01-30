import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders, screen, waitFor, userEvent } from '../../test/utils'
import { mockData, apiCallLog, resetApiCallLog } from '../../test/mocks/handlers'
import { PlaylistsPage } from '../../pages/PlaylistsPage'

describe('Playlist Flow Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetApiCallLog()
    // Clear localStorage to start fresh
    localStorage.clear()
  })

  describe('View and Select Playlist Flow', () => {
    it('displays playlist list from API', async () => {
      renderWithProviders(<PlaylistsPage />)

      await waitFor(() => {
        expect(screen.getByText('default')).toBeInTheDocument()
        expect(screen.getByText('favorites')).toBeInTheDocument()
        expect(screen.getByText('geometric')).toBeInTheDocument()
      })
    })

    it('displays page title and count', async () => {
      renderWithProviders(<PlaylistsPage />)

      await waitFor(() => {
        expect(screen.getByText('Playlists')).toBeInTheDocument()
        expect(screen.getByText(/3 playlists/i)).toBeInTheDocument()
      })
    })

    it('clicking playlist selects it and loads patterns', async () => {
      const user = userEvent.setup()
      renderWithProviders(<PlaylistsPage />)

      await waitFor(() => {
        expect(screen.getByText('default')).toBeInTheDocument()
      })

      // Click on default playlist
      await user.click(screen.getByText('default'))

      // Should show playlist content with pattern count
      await waitFor(() => {
        // default playlist has 2 patterns
        expect(screen.getByText(/2 patterns/i)).toBeInTheDocument()
      })
    })
  })

  describe('Run Playlist Flow', () => {
    it('runs existing playlist and verifies API call', async () => {
      const user = userEvent.setup()
      renderWithProviders(<PlaylistsPage />)

      await waitFor(() => {
        expect(screen.getByText('default')).toBeInTheDocument()
      })

      // Click playlist to select it
      await user.click(screen.getByText('default'))

      // Wait for patterns to load
      await waitFor(() => {
        expect(screen.getByText(/2 patterns/i)).toBeInTheDocument()
      })

      // Find the play button (circular button with play_arrow icon)
      // It's a button that contains a play_arrow material icon
      const buttons = screen.getAllByRole('button')
      const playButton = buttons.find(btn =>
        btn.querySelector('.material-icons')?.textContent === 'play_arrow'
      )
      expect(playButton).toBeTruthy()

      await user.click(playButton!)

      // Verify API call
      await waitFor(() => {
        const runCall = apiCallLog.find(c => c.endpoint === '/run_playlist')
        expect(runCall).toBeDefined()
        expect(runCall?.body).toMatchObject({
          playlist_name: 'default'
        })
      })

      // Verify state updated
      expect(mockData.status.is_running).toBe(true)
      expect(mockData.status.playlist_mode).toBe(true)
      expect(mockData.status.playlist_name).toBe('default')
    })

    it('populates queue from playlist files when running', async () => {
      const user = userEvent.setup()
      renderWithProviders(<PlaylistsPage />)

      await waitFor(() => {
        expect(screen.getByText('default')).toBeInTheDocument()
      })

      // default playlist has: ['patterns/star.thr', 'patterns/spiral.thr']
      const initialPlaylist = mockData.playlists['default']
      expect(initialPlaylist.length).toBe(2)

      // Click and run
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

      // Verify queue was set correctly
      await waitFor(() => {
        expect(mockData.status.current_file).toBe('patterns/star.thr')
        expect(mockData.status.queue).toContain('patterns/spiral.thr')
      })
    })
  })

  describe('Create Playlist Flow', () => {
    it('creates new playlist via dialog', async () => {
      const user = userEvent.setup()
      renderWithProviders(<PlaylistsPage />)

      // Wait for page to load
      await waitFor(() => {
        expect(screen.getByText('default')).toBeInTheDocument()
      })

      // Click create button (the + icon button in sidebar header)
      const buttons = screen.getAllByRole('button')
      const addButton = buttons.find(btn => {
        const icon = btn.querySelector('.material-icons-outlined')
        return icon?.textContent === 'add'
      })

      expect(addButton).toBeTruthy()
      await user.click(addButton!)

      // Fill in dialog
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })

      const nameInput = screen.getByPlaceholderText(/favorites.*morning.*patterns/i)
      await user.type(nameInput, 'my-test-playlist')

      // Submit by clicking Create Playlist button
      const submitButton = screen.getByRole('button', { name: /create playlist/i })
      await user.click(submitButton)

      // Verify API call
      await waitFor(() => {
        const createCall = apiCallLog.find(c => c.endpoint === '/create_playlist')
        expect(createCall).toBeDefined()
        expect(createCall?.body).toMatchObject({
          playlist_name: 'my-test-playlist'
        })
      })

      // Verify mockData was updated
      expect(mockData.playlists['my-test-playlist']).toBeDefined()
    })
  })

  describe('Delete Playlist Flow', () => {
    it('deletes playlist after confirmation', async () => {
      const user = userEvent.setup()

      // Add a test playlist to delete
      mockData.playlists['to-delete'] = ['patterns/star.thr']

      renderWithProviders(<PlaylistsPage />)

      await waitFor(() => {
        expect(screen.getByText('to-delete')).toBeInTheDocument()
      })

      // Find and hover over the playlist item to reveal delete button
      const playlistItem = screen.getByText('to-delete')

      // The delete button is a sibling of the text
      const parentDiv = playlistItem.closest('[class*="group"]')
      expect(parentDiv).toBeTruthy()

      // Find delete button within the same row (uses Trash2 lucide icon with text-destructive class)
      const deleteButtons = parentDiv!.querySelectorAll('button')
      const deleteButton = Array.from(deleteButtons).find(btn =>
        btn.classList.contains('text-destructive') || btn.className.includes('text-destructive')
      )

      expect(deleteButton).toBeTruthy()

      // Mock window.confirm
      const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

      await user.click(deleteButton!)

      // Verify confirm was called
      expect(confirmSpy).toHaveBeenCalled()

      // Verify API call
      await waitFor(() => {
        const deleteCall = apiCallLog.find(c => c.endpoint === '/delete_playlist')
        expect(deleteCall).toBeDefined()
      })

      // Verify mockData was updated
      expect(mockData.playlists['to-delete']).toBeUndefined()

      confirmSpy.mockRestore()
    })
  })

  describe('Playlist State Verification', () => {
    it('verifies run_playlist API call format', async () => {
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

      // Verify complete API call structure
      await waitFor(() => {
        const runCall = apiCallLog.find(c => c.endpoint === '/run_playlist')
        expect(runCall).toBeDefined()
        expect(runCall?.method).toBe('POST')
        expect(runCall?.timestamp).toBeDefined()
        expect(runCall?.body).toHaveProperty('playlist_name')
      })
    })
  })
})
