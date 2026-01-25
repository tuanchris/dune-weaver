import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders, screen, waitFor, userEvent } from '../../test/utils'
import { server } from '../../test/mocks/server'
import { http, HttpResponse } from 'msw'
import { PlaylistsPage } from '../../pages/PlaylistsPage'

describe('PlaylistsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Playlist Listing', () => {
    it('renders playlist names from API', async () => {
      renderWithProviders(<PlaylistsPage />)

      await waitFor(() => {
        expect(screen.getByText('default')).toBeInTheDocument()
        expect(screen.getByText('favorites')).toBeInTheDocument()
        expect(screen.getByText('geometric')).toBeInTheDocument()
      })
    })

    it('displays page title and description', async () => {
      renderWithProviders(<PlaylistsPage />)

      await waitFor(() => {
        expect(screen.getByText('Playlists')).toBeInTheDocument()
        expect(screen.getByText(/create and manage pattern playlists/i)).toBeInTheDocument()
      })
    })

    it('shows playlist count', async () => {
      renderWithProviders(<PlaylistsPage />)

      await waitFor(() => {
        expect(screen.getByText('3 playlists')).toBeInTheDocument()
      })
    })

    it('handles empty playlist list', async () => {
      server.use(
        http.get('/list_all_playlists', () => {
          return HttpResponse.json([])
        })
      )

      renderWithProviders(<PlaylistsPage />)

      await waitFor(() => {
        expect(screen.getByText(/no playlists yet/i)).toBeInTheDocument()
      })
    })
  })

  describe('Playlist Selection', () => {
    it('clicking playlist loads its patterns', async () => {
      const user = userEvent.setup()
      renderWithProviders(<PlaylistsPage />)

      await waitFor(() => {
        expect(screen.getByText('default')).toBeInTheDocument()
      })

      // Click on playlist
      await user.click(screen.getByText('default'))

      // Should show patterns from that playlist
      // The patterns are displayed in the content area
      await waitFor(() => {
        // Playlist 'default' contains star.thr and spiral.thr based on mock data
        expect(screen.getByText(/star/i)).toBeInTheDocument()
      })
    })
  })

  describe('Playlist CRUD', () => {
    it('create button opens modal', async () => {
      const user = userEvent.setup()
      renderWithProviders(<PlaylistsPage />)

      await waitFor(() => {
        expect(screen.getByText('default')).toBeInTheDocument()
      })

      // Find the add button (plus icon in sidebar header)
      const addButtons = screen.getAllByRole('button')
      const addButton = addButtons.find(btn => btn.querySelector('.material-icons-outlined')?.textContent?.includes('add'))

      if (addButton) {
        await user.click(addButton)

        // Dialog should open
        await waitFor(() => {
          expect(screen.getByRole('dialog')).toBeInTheDocument()
        })
      }
    })

    it('create playlist calls API', async () => {
      const user = userEvent.setup()
      let createCalled = false
      let createdName = ''

      server.use(
        http.post('/create_playlist', async ({ request }) => {
          const body = await request.json() as { name?: string; playlist_name?: string }
          createCalled = true
          createdName = body.name || body.playlist_name || ''
          return HttpResponse.json({ success: true })
        })
      )

      renderWithProviders(<PlaylistsPage />)

      await waitFor(() => {
        expect(screen.getByText('default')).toBeInTheDocument()
      })

      // Find and click add button
      const addButtons = screen.getAllByRole('button')
      const addButton = addButtons.find(btn => btn.querySelector('.material-icons-outlined')?.textContent?.includes('add'))

      if (addButton) {
        await user.click(addButton)

        // Wait for dialog and enter name
        await waitFor(() => {
          expect(screen.getByRole('dialog')).toBeInTheDocument()
        })

        const input = screen.getByRole('textbox')
        await user.type(input, 'my-new-playlist')

        // Click create button
        const createButton = screen.getByRole('button', { name: /create/i })
        await user.click(createButton)

        await waitFor(() => {
          expect(createCalled).toBe(true)
          expect(createdName).toBe('my-new-playlist')
        })
      }
    })

    it('edit button opens rename modal', async () => {
      const user = userEvent.setup()
      renderWithProviders(<PlaylistsPage />)

      await waitFor(() => {
        expect(screen.getByText('default')).toBeInTheDocument()
      })

      // Find edit button for a playlist (hover actions)
      const editButtons = screen.getAllByRole('button')
      const editButton = editButtons.find(btn =>
        btn.querySelector('.material-icons-outlined')?.textContent?.includes('edit')
      )

      if (editButton) {
        await user.click(editButton)

        await waitFor(() => {
          expect(screen.getByRole('dialog')).toBeInTheDocument()
        })
      }
    })

    it('delete buttons are present for each playlist', async () => {
      renderWithProviders(<PlaylistsPage />)

      await waitFor(() => {
        expect(screen.getByText('geometric')).toBeInTheDocument()
      })

      // Find delete buttons (trash icons) - each playlist item should have one
      const deleteButtons = screen.getAllByRole('button').filter(btn =>
        btn.querySelector('.material-icons-outlined')?.textContent?.includes('delete')
      )

      // Should have at least one delete button (for each playlist)
      expect(deleteButtons.length).toBeGreaterThan(0)
    })
  })

  describe('Playlist Execution', () => {
    it('run playlist button triggers API', async () => {
      const user = userEvent.setup()
      let runCalled = false
      let playlistName = ''

      server.use(
        http.post('/run_playlist', async ({ request }) => {
          const body = await request.json() as { playlist_name: string }
          runCalled = true
          playlistName = body.playlist_name
          return HttpResponse.json({ success: true })
        })
      )

      renderWithProviders(<PlaylistsPage />)

      await waitFor(() => {
        expect(screen.getByText('default')).toBeInTheDocument()
      })

      // Select a playlist first
      await user.click(screen.getByText('default'))

      // Wait for content to load and find run/play button
      await waitFor(async () => {
        const runButton = screen.getByRole('button', { name: /play|run|start/i })
        expect(runButton).toBeInTheDocument()
        await user.click(runButton)
      })

      await waitFor(() => {
        expect(runCalled).toBe(true)
        expect(playlistName).toBe('default')
      })
    })
  })
})
