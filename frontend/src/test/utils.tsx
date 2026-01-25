import { render, RenderOptions } from '@testing-library/react'
import { BrowserRouter } from 'react-router'
import { ReactElement, ReactNode } from 'react'
import { PatternMetadata, PreviewData } from '@/lib/types'

// Wrapper component with required providers
function AllProviders({ children }: { children: ReactNode }) {
  return <BrowserRouter>{children}</BrowserRouter>
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

// Re-export everything from testing-library
export * from '@testing-library/react'
export { default as userEvent } from '@testing-library/user-event'
