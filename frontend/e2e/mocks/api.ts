import { Page, WebSocketRoute } from '@playwright/test'

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
    const body = route.request().postDataJSON() as { playlist_name?: string; name?: string }
    // Support both playlist_name (actual API) and name (legacy)
    const playlistName = body?.playlist_name || body?.name
    const playlist = mockPlaylists[playlistName as keyof typeof mockPlaylists]
    if (playlist && playlist.length > 0) {
      currentStatus.is_running = true
      currentStatus.playlist_mode = true
      currentStatus.playlist_name = playlistName || null
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

  // Logs endpoint
  await page.route('**/api/logs**', async route => {
    await route.fulfill({ json: { logs: [], total: 0, has_more: false } })
  })

  // Pattern history (individual)
  await page.route('**/api/pattern_history/**', async route => {
    await route.fulfill({ json: { actual_time_formatted: null, speed: null } })
  })

  // Serial ports
  await page.route('**/list_serial_ports', async route => {
    await route.fulfill({ json: [] })
  })

  // Static files - return 200 with placeholder
  await page.route('**/static/**', async route => {
    // Return a 1x1 transparent PNG for images
    const base64Png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
    await route.fulfill({
      status: 200,
      contentType: 'image/png',
      body: Buffer.from(base64Png, 'base64'),
    })
  })

  // WebSocket mocking - critical for bypassing the "Connecting to Backend" overlay
  // The Layout component shows a blocking overlay until WebSocket connects
  await page.routeWebSocket('**/ws/status', (ws: WebSocketRoute) => {
    // Don't connect to server - we're mocking everything
    // Send status updates to simulate backend status messages
    const statusMessage = JSON.stringify({
      type: 'status_update',
      data: {
        ...currentStatus,
        connection_status: true,
        is_homing: false,
      }
    })

    // Send initial status immediately after connection
    // The client's onopen handler will fire, setting isBackendConnected = true
    setTimeout(() => {
      ws.send(statusMessage)
    }, 100)

    // Send periodic updates
    const interval = setInterval(() => {
      ws.send(statusMessage)
    }, 1000)

    ws.onClose(() => {
      clearInterval(interval)
    })
  })

  // Mock other WebSocket endpoints
  await page.routeWebSocket('**/ws/logs', (_ws: WebSocketRoute) => {
    // Just accept the connection - don't need to send anything
  })

  await page.routeWebSocket('**/ws/cache-progress', (ws: WebSocketRoute) => {
    // Send "not running" status
    setTimeout(() => {
      ws.send(JSON.stringify({
        type: 'cache_progress',
        data: { is_running: false, stage: 'idle' }
      }))
    }, 100)
  })
}

export function getMockStatus() {
  return { ...currentStatus }
}

export function setMockStatus(updates: Partial<typeof currentStatus>) {
  Object.assign(currentStatus, updates)
}
