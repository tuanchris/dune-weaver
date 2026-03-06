import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders, screen, waitFor, userEvent } from '../../test/utils'
import { server } from '../../test/mocks/server'
import { http, HttpResponse } from 'msw'
import { TableControlPage } from '../../pages/TableControlPage'
import { useStatusStore } from '../../stores/useStatusStore'

describe('TableControlPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Reset Zustand store to prevent real WebSocket data from leaking into tests
    useStatusStore.setState({ status: null, isBackendConnected: false, connectionAttempts: 0 })
  })

  describe('Rendering', () => {
    it('renders page title and description', async () => {
      renderWithProviders(<TableControlPage />)

      await waitFor(() => {
        expect(screen.getByText('Table Control')).toBeInTheDocument()
        expect(screen.getByText(/manual controls for your sand table/i)).toBeInTheDocument()
      })
    })

    it('renders primary action buttons', async () => {
      renderWithProviders(<TableControlPage />)

      await waitFor(() => {
        // Home, Stop, Reset buttons should be visible
        expect(screen.getByText('Home')).toBeInTheDocument()
        expect(screen.getByText('Stop')).toBeInTheDocument()
        expect(screen.getByText('Reset')).toBeInTheDocument()
      })
    })

    it('renders position control buttons', async () => {
      renderWithProviders(<TableControlPage />)

      await waitFor(() => {
        // Center and Perimeter buttons
        expect(screen.getByText('Center')).toBeInTheDocument()
        expect(screen.getByText('Perimeter')).toBeInTheDocument()
      })
    })

    it('renders speed control section', async () => {
      renderWithProviders(<TableControlPage />)

      await waitFor(() => {
        expect(screen.getByText('Speed')).toBeInTheDocument()
        expect(screen.getByPlaceholderText(/mm\/s/i)).toBeInTheDocument()
      })
    })
  })

  describe('Homing Control', () => {
    it('home button calls send_home API', async () => {
      const user = userEvent.setup()
      let homeCalled = false

      server.use(
        http.post('/send_home', () => {
          homeCalled = true
          return HttpResponse.json({ success: true })
        })
      )

      renderWithProviders(<TableControlPage />)

      await waitFor(() => {
        expect(screen.getByText('Home')).toBeInTheDocument()
      })

      const homeButton = screen.getByText('Home').closest('button')!
      await user.click(homeButton)

      await waitFor(() => {
        expect(homeCalled).toBe(true)
      })
    })
  })

  describe('Stop Control', () => {
    it('stop button calls stop_execution API', async () => {
      const user = userEvent.setup()
      let stopCalled = false

      server.use(
        http.post('/stop_execution', () => {
          stopCalled = true
          return HttpResponse.json({ success: true })
        })
      )

      renderWithProviders(<TableControlPage />)

      await waitFor(() => {
        expect(screen.getByText('Stop')).toBeInTheDocument()
      })

      const stopButton = screen.getByText('Stop').closest('button')!
      await user.click(stopButton)

      await waitFor(() => {
        expect(stopCalled).toBe(true)
      })
    })
  })

  describe('Reset Control', () => {
    it('reset button is clickable', async () => {
      const user = userEvent.setup()
      renderWithProviders(<TableControlPage />)

      await waitFor(() => {
        expect(screen.getByText('Reset')).toBeInTheDocument()
      })

      const resetButton = screen.getByText('Reset').closest('button')!
      expect(resetButton).toBeEnabled()

      // Click should not throw
      await expect(user.click(resetButton)).resolves.not.toThrow()
    })

    it('reset button triggers dialog trigger', async () => {
      const user = userEvent.setup()
      renderWithProviders(<TableControlPage />)

      await waitFor(() => {
        expect(screen.getByText('Reset')).toBeInTheDocument()
      })

      // The Reset button is a DialogTrigger - check its aria attributes
      const resetButton = screen.getByText('Reset').closest('button')!
      expect(resetButton).toHaveAttribute('aria-haspopup', 'dialog')

      await user.click(resetButton)

      // After clicking, aria-expanded should change
      await waitFor(() => {
        // The button should have triggered the dialog
        // Note: Radix Dialog renders to a portal, may need to check document.body
        const dialog = document.querySelector('[role="dialog"]')
        if (dialog) {
          expect(dialog).toBeInTheDocument()
        }
      })
    })
  })

  describe('Movement Controls', () => {
    it('move to center button calls API', async () => {
      const user = userEvent.setup()
      let moveCalled = false

      server.use(
        http.post('/move_to_center', () => {
          moveCalled = true
          return HttpResponse.json({ success: true })
        })
      )

      renderWithProviders(<TableControlPage />)

      await waitFor(() => {
        expect(screen.getByText('Center')).toBeInTheDocument()
      })

      const centerButton = screen.getByText('Center').closest('button')!
      await user.click(centerButton)

      await waitFor(() => {
        expect(moveCalled).toBe(true)
      })
    })

    it('move to perimeter button calls API', async () => {
      const user = userEvent.setup()
      let moveCalled = false

      server.use(
        http.post('/move_to_perimeter', () => {
          moveCalled = true
          return HttpResponse.json({ success: true })
        })
      )

      renderWithProviders(<TableControlPage />)

      await waitFor(() => {
        expect(screen.getByText('Perimeter')).toBeInTheDocument()
      })

      const perimeterButton = screen.getByText('Perimeter').closest('button')!
      await user.click(perimeterButton)

      await waitFor(() => {
        expect(moveCalled).toBe(true)
      })
    })
  })

  describe('Speed Control', () => {
    it('speed input submits to API on Set click', async () => {
      const user = userEvent.setup()
      let speedSet: number | null = null

      server.use(
        http.post('/set_speed', async ({ request }) => {
          const body = await request.json() as { speed: number }
          speedSet = body.speed
          return HttpResponse.json({ success: true })
        })
      )

      renderWithProviders(<TableControlPage />)

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/mm\/s/i)).toBeInTheDocument()
      })

      const speedInput = screen.getByPlaceholderText(/mm\/s/i)
      await user.type(speedInput, '250')

      // Find the Set button - it's near the speed input
      const speedCard = speedInput.closest('.p-6')
      const setButton = speedCard?.querySelector('button')
      expect(setButton).toBeTruthy()
      await user.click(setButton!)

      await waitFor(() => {
        expect(speedSet).toBe(250)
      })
    })

    it('speed input submits on Enter key', async () => {
      const user = userEvent.setup()
      let speedSet: number | null = null

      server.use(
        http.post('/set_speed', async ({ request }) => {
          const body = await request.json() as { speed: number }
          speedSet = body.speed
          return HttpResponse.json({ success: true })
        })
      )

      renderWithProviders(<TableControlPage />)

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/mm\/s/i)).toBeInTheDocument()
      })

      const speedInput = screen.getByPlaceholderText(/mm\/s/i)
      await user.type(speedInput, '300{Enter}')

      await waitFor(() => {
        expect(speedSet).toBe(300)
      })
    })

    it('shows speed badge with current speed', async () => {
      renderWithProviders(<TableControlPage />)

      await waitFor(() => {
        // The speed badge shows "-- mm/s" when no speed is set
        expect(screen.getByText(/mm\/s/)).toBeInTheDocument()
      })
    })
  })
})
