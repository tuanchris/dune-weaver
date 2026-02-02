import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders, screen, waitFor, userEvent } from '../../test/utils'
import { server } from '../../test/mocks/server'
import { http, HttpResponse } from 'msw'
import { BrowsePage } from '../../pages/BrowsePage'

describe('BrowsePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Pattern Listing', () => {
    it('renders pattern list from API', async () => {
      renderWithProviders(<BrowsePage />)

      await waitFor(() => {
        expect(screen.getByText('star.thr')).toBeInTheDocument()
        expect(screen.getByText('spiral.thr')).toBeInTheDocument()
        expect(screen.getByText('wave.thr')).toBeInTheDocument()
      })
    })

    it('displays page title', async () => {
      renderWithProviders(<BrowsePage />)

      await waitFor(() => {
        expect(screen.getByText('Browse Patterns')).toBeInTheDocument()
      })
    })

    it('handles empty pattern list', async () => {
      server.use(
        http.get('/list_theta_rho_files_with_metadata', () => {
          return HttpResponse.json([])
        })
      )

      renderWithProviders(<BrowsePage />)

      await waitFor(() => {
        expect(screen.getByText(/no patterns found/i)).toBeInTheDocument()
      })
    })

    it('handles API error gracefully', async () => {
      server.use(
        http.get('/list_theta_rho_files_with_metadata', () => {
          return HttpResponse.error()
        })
      )

      renderWithProviders(<BrowsePage />)

      // Should not crash - page should still render
      await waitFor(() => {
        expect(screen.getByText('Browse Patterns')).toBeInTheDocument()
      })
    })
  })

  describe('Pattern Selection', () => {
    it('clicking pattern opens detail sheet', async () => {
      const user = userEvent.setup()
      renderWithProviders(<BrowsePage />)

      await waitFor(() => {
        expect(screen.getByText('star.thr')).toBeInTheDocument()
      })

      // Click on a pattern
      await user.click(screen.getByText('star.thr'))

      // Sheet should open with pattern name in title
      await waitFor(() => {
        // The Sheet title contains the pattern name
        const titles = screen.getAllByText('star.thr')
        expect(titles.length).toBeGreaterThan(1) // One in card, one in sheet title
      })
    })
  })

  describe('Search and Filter', () => {
    it('search filters patterns by name', async () => {
      const user = userEvent.setup()
      renderWithProviders(<BrowsePage />)

      await waitFor(() => {
        expect(screen.getByText('star.thr')).toBeInTheDocument()
      })

      // Find and type in search input
      const searchInput = screen.getByPlaceholderText(/search/i)
      await user.type(searchInput, 'star')

      await waitFor(() => {
        expect(screen.getByText('star.thr')).toBeInTheDocument()
        expect(screen.queryByText('spiral.thr')).not.toBeInTheDocument()
      })
    })

    it('clearing search shows all patterns', async () => {
      const user = userEvent.setup()
      renderWithProviders(<BrowsePage />)

      await waitFor(() => {
        expect(screen.getByText('star.thr')).toBeInTheDocument()
      })

      const searchInput = screen.getByPlaceholderText(/search/i)
      await user.type(searchInput, 'star')

      await waitFor(() => {
        expect(screen.queryByText('spiral.thr')).not.toBeInTheDocument()
      })

      await user.clear(searchInput)

      await waitFor(() => {
        expect(screen.getByText('star.thr')).toBeInTheDocument()
        expect(screen.getByText('spiral.thr')).toBeInTheDocument()
      })
    })

    it('no results message shows clear filters button', async () => {
      const user = userEvent.setup()
      renderWithProviders(<BrowsePage />)

      await waitFor(() => {
        expect(screen.getByText('star.thr')).toBeInTheDocument()
      })

      const searchInput = screen.getByPlaceholderText(/search/i)
      await user.type(searchInput, 'nonexistentpattern')

      await waitFor(() => {
        expect(screen.getByText(/no patterns found/i)).toBeInTheDocument()
        expect(screen.getByText(/clear filters/i)).toBeInTheDocument()
      })
    })
  })

  describe('Pattern Actions', () => {
    it('clicking pattern opens sheet with pattern details', async () => {
      const user = userEvent.setup()

      renderWithProviders(<BrowsePage />)

      await waitFor(() => {
        expect(screen.getByText('star.thr')).toBeInTheDocument()
      })

      // Click pattern to open detail sheet
      await user.click(screen.getByText('star.thr'))

      // Sheet should open - the pattern name appears twice (once in list, once in sheet title)
      await waitFor(() => {
        const patternNames = screen.getAllByText('star.thr')
        expect(patternNames.length).toBeGreaterThan(1)
      })
    })

    it('pattern cards are clickable', async () => {
      const user = userEvent.setup()

      renderWithProviders(<BrowsePage />)

      await waitFor(() => {
        expect(screen.getByText('star.thr')).toBeInTheDocument()
      })

      // Pattern cards should be clickable
      const patternCard = screen.getByText('star.thr')
      await expect(user.click(patternCard)).resolves.not.toThrow()
    })
  })
})
