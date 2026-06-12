import { render } from '@testing-library/react'
import type { RenderOptions } from '@testing-library/react'
// Import from 'react-router-dom' (same as app code) — under vitest the two
// packages load as separate module instances, so a Router from 'react-router'
// provides context that app <Link>s from 'react-router-dom' cannot see
import { BrowserRouter, MemoryRouter, Routes, Route } from 'react-router-dom'
import type { ReactElement, ReactNode } from 'react'
import type { PatternMetadata, PreviewData } from '@/lib/types'
import { useStatusStore } from '@/stores/useStatusStore'
import type { StatusData } from '@/stores/useStatusStore'
import { TableProvider } from '@/contexts/TableContext'
import { Layout } from '@/components/layout/Layout'
import { BrowsePage } from '@/pages/BrowsePage'
import { PlaylistsPage } from '@/pages/PlaylistsPage'
import { TableControlPage } from '@/pages/TableControlPage'

// Wrapper component with required providers
function AllProviders({ children }: { children: ReactNode }) {
  return <BrowserRouter>{children}</BrowserRouter>
}

// Integration test wrapper - full app with routing
export function IntegrationWrapper({
  children,
  initialEntries = ['/']
}: {
  children: ReactNode
  initialEntries?: string[]
}) {
  return (
    <MemoryRouter initialEntries={initialEntries}>
      <TableProvider>
        {children}
      </TableProvider>
    </MemoryRouter>
  )
}

// Custom render that includes providers
export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>
) {
  return render(ui, { wrapper: AllProviders, ...options })
}

// Mock data generators
export function createMockPatterns(count: number = 5): PatternMetadata[] {
  return Array.from({ length: count }, (_, i) => ({
    path: `patterns/pattern${i + 1}.thr`,
    name: `pattern${i + 1}.thr`,
    category: i % 2 === 0 ? 'geometric' : 'organic',
    date_modified: Date.now() - i * 86400000, // Each day older
    coordinates_count: 100 + i * 50,
  }))
}

export function createMockPreview(): PreviewData {
  // 1x1 transparent PNG as base64
  return {
    image_data: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
    first_coordinate: { x: 0, y: 0 },
    last_coordinate: { x: 100, y: 100 },
  }
}

export function createMockStatus(overrides: Partial<{
  is_running: boolean
  is_paused: boolean
  current_file: string | null
  speed: number
  progress: number
  playlist_mode: boolean
  playlist_name: string | null
  queue: string[]
}> = {}) {
  return {
    is_running: false,
    is_paused: false,
    current_file: null,
    speed: 100,
    progress: 0,
    playlist_mode: false,
    playlist_name: null,
    queue: [],
    connection_status: 'connected',
    ...overrides,
  }
}

export function createMockPlaylists(): string[] {
  return ['default', 'favorites', 'geometric', 'relaxing']
}

// Seed the status store as a connected, idle table. Pages gate actions
// (e.g. BrowsePage's Play button) on status.connection_status, which in
// the app only arrives over the /ws/status WebSocket.
export function seedConnectedStatus(overrides: Partial<StatusData> = {}) {
  useStatusStore.setState({
    status: {
      current_file: null,
      is_paused: false,
      manual_pause: false,
      scheduled_pause: false,
      is_running: false,
      is_homing: false,
      is_clearing: false,
      sensor_homing_failed: false,
      progress: null,
      playlist: null,
      speed: 100,
      pause_time_remaining: 0,
      original_pause_time: null,
      connection_status: true,
      current_theta: 0,
      current_rho: 0,
      firmware_version: null,
      table_type: null,
      ...overrides,
    },
  })
}

// Render full app for integration tests
export function renderApp(options?: {
  initialRoute?: string
}) {
  const initialEntries = options?.initialRoute ? [options.initialRoute] : ['/']

  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <TableProvider>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<BrowsePage />} />
            <Route path="playlists" element={<PlaylistsPage />} />
            <Route path="table-control" element={<TableControlPage />} />
          </Route>
        </Routes>
      </TableProvider>
    </MemoryRouter>
  )
}

// Re-export everything from testing-library
export * from '@testing-library/react'
export { default as userEvent } from '@testing-library/user-event'
