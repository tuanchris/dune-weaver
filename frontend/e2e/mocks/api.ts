import { Page } from '@playwright/test'

// Mock data
export const mockPatterns = [
  { path: 'patterns/star.thr', name: 'star.thr', category: 'geometric', date_modified: Date.now(), coordinates_count: 150 },
  { path: 'patterns/spiral.thr', name: 'spiral.thr', category: 'organic', date_modified: Date.now(), coordinates_count: 200 },
  { path: 'patterns/wave.thr', name: 'wave.thr', category: 'organic', date_modified: Date.now(), coordinates_count: 175 },
]

export const mockPlaylists = {
  default: ['patterns/star.thr', 'patterns/spiral.thr'],
  favorites: ['patterns/star.thr'],
}

// Mutable status for simulating playback
let currentStatus = {
  is_running: false,
  is_paused: false,
  current_file: null as string | null,
  speed: 100,
  progress: 0,
  playlist_mode: false,
  playlist_name: null as string | null,
  queue: [] as string[],
  connection_status: 'connected',
  theta: 0,
  rho: 0.5,
}

export function resetMockStatus() {
  currentStatus = {
    is_running: false,
    is_paused: false,
    current_file: null,
    speed: 100,
    progress: 0,
    playlist_mode: false,
    playlist_name: null,
    queue: [],
    connection_status: 'connected',
    theta: 0,
    rho: 0.5,
  }
}

export async function setupApiMocks(page: Page) {
  // Pattern endpoints
  await page.route('**/list_theta_rho_files_with_metadata', async route => {
    await route.fulfill({ json: mockPatterns })
  })

  await page.route('**/list_theta_rho_files', async route => {
    await route.fulfill({ json: mockPatterns.map(p => ({ name: p.name, path: p.path })) })
  })

  await page.route('**/preview_thr_batch', async route => {
    const request = route.request()
    const body = request.postDataJSON() as { files: string[] }
    const previews: Record<string, unknown> = {}
    for (const file of body?.files || []) {
      previews[file] = {
        image_data: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
        first_coordinate: { x: 0, y: 0 },
        last_coordinate: { x: 100, y: 100 },
      }
    }
    await route.fulfill({ json: previews })
  })

  await page.route('**/run_theta_rho', async route => {
    const body = route.request().postDataJSON() as { file_name?: string; file?: string }
    const file = body?.file_name || body?.file || null
    currentStatus.is_running = true
    currentStatus.current_file = file
    await route.fulfill({ json: { success: true } })
  })

  // Playlist endpoints
  await page.route('**/list_all_playlists', async route => {
    await route.fulfill({ json: Object.keys(mockPlaylists) })
  })

  await page.route('**/get_playlist**', async route => {
    const url = new URL(route.request().url())
    const name = url.searchParams.get('name') || ''
    await route.fulfill({
      json: { name, files: mockPlaylists[name as keyof typeof mockPlaylists] || [] }
    })
  })

  await page.route('**/run_playlist', async route => {
    const body = route.request().postDataJSON() as { name: string }
    const playlist = mockPlaylists[body?.name as keyof typeof mockPlaylists]
    if (playlist && playlist.length > 0) {
      currentStatus.is_running = true
      currentStatus.playlist_mode = true
      currentStatus.playlist_name = body.name
      currentStatus.current_file = playlist[0]
      currentStatus.queue = playlist.slice(1)
    }
    await route.fulfill({ json: { success: true } })
  })

  // Playback control endpoints
  await page.route('**/pause_execution', async route => {
    currentStatus.is_paused = true
    await route.fulfill({ json: { success: true } })
  })

  await page.route('**/resume_execution', async route => {
    currentStatus.is_paused = false
    await route.fulfill({ json: { success: true } })
  })

  await page.route('**/stop_execution', async route => {
    currentStatus.is_running = false
    currentStatus.is_paused = false
    currentStatus.current_file = null
    currentStatus.playlist_mode = false
    currentStatus.queue = []
    await route.fulfill({ json: { success: true } })
  })

  // Status endpoint
  await page.route('**/serial_status', async route => {
    await route.fulfill({ json: currentStatus })
  })

  // Table info (for TableContext)
  await page.route('**/api/table-info', async route => {
    await route.fulfill({
      json: { id: 'test-table', name: 'Test Table', version: '1.0.0' }
    })
  })

  // Settings
  await page.route('**/api/settings', async route => {
    await route.fulfill({ json: { app: { name: 'Dune Weaver' } } })
  })

  // Known tables
  await page.route('**/api/known-tables', async route => {
    await route.fulfill({ json: { tables: [] } })
  })

  // Pattern history
  await page.route('**/api/pattern_history_all', async route => {
    await route.fulfill({ json: {} })
  })

  // WebSocket - return empty to prevent connection attempts
  // Playwright doesn't intercept WebSocket by default, but we can handle the fallback
}

export function getMockStatus() {
  return { ...currentStatus }
}

export function setMockStatus(updates: Partial<typeof currentStatus>) {
  Object.assign(currentStatus, updates)
}
