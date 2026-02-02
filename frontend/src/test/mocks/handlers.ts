import { http, HttpResponse } from 'msw'
import type { PatternMetadata, PreviewData } from '@/lib/types'

// ============================================
// API Call Tracking for Integration Tests
// ============================================

// Track API calls for integration test verification
export const apiCallLog: Array<{
  endpoint: string
  method: string
  body?: unknown
  timestamp: number
}> = []

export function resetApiCallLog() {
  apiCallLog.length = 0
}

// Helper to log API calls
function logApiCall(endpoint: string, method: string, body?: unknown) {
  apiCallLog.push({
    endpoint,
    method,
    body,
    timestamp: Date.now(),
  })
}

// ============================================
// Mock Data Store (mutable for test scenarios)
// ============================================

export const mockData = {
  patterns: [
    { path: 'patterns/star.thr', name: 'star.thr', category: 'geometric', date_modified: Date.now(), coordinates_count: 150 },
    { path: 'patterns/spiral.thr', name: 'spiral.thr', category: 'organic', date_modified: Date.now() - 86400000, coordinates_count: 200 },
    { path: 'patterns/wave.thr', name: 'wave.thr', category: 'organic', date_modified: Date.now() - 172800000, coordinates_count: 175 },
    { path: 'patterns/custom/my_design.thr', name: 'my_design.thr', category: 'custom', date_modified: Date.now() - 259200000, coordinates_count: 100 },
  ] as PatternMetadata[],

  playlists: {
    default: ['patterns/star.thr', 'patterns/spiral.thr'],
    favorites: ['patterns/star.thr'],
    geometric: ['patterns/star.thr', 'patterns/wave.thr'],
  } as Record<string, string[]>,

  status: {
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
  },
}

// Reset mock data between tests
export function resetMockData() {
  mockData.patterns = [
    { path: 'patterns/star.thr', name: 'star.thr', category: 'geometric', date_modified: Date.now(), coordinates_count: 150 },
    { path: 'patterns/spiral.thr', name: 'spiral.thr', category: 'organic', date_modified: Date.now() - 86400000, coordinates_count: 200 },
    { path: 'patterns/wave.thr', name: 'wave.thr', category: 'organic', date_modified: Date.now() - 172800000, coordinates_count: 175 },
    { path: 'patterns/custom/my_design.thr', name: 'my_design.thr', category: 'custom', date_modified: Date.now() - 259200000, coordinates_count: 100 },
  ]
  mockData.playlists = {
    default: ['patterns/star.thr', 'patterns/spiral.thr'],
    favorites: ['patterns/star.thr'],
    geometric: ['patterns/star.thr', 'patterns/wave.thr'],
  }
  mockData.status = {
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

// ============================================
// Handlers
// ============================================

export const handlers = [
  // ----------------
  // Pattern Endpoints
  // ----------------
  http.get('/list_theta_rho_files', () => {
    return HttpResponse.json(mockData.patterns.map(p => ({ name: p.name, path: p.path })))
  }),

  http.get('/list_theta_rho_files_with_metadata', () => {
    return HttpResponse.json(mockData.patterns)
  }),

  http.post('/preview_thr_batch', async ({ request }) => {
    const body = await request.json() as { files?: string[]; file_names?: string[] }
    const files = body.files || body.file_names || []
    const previews: Record<string, PreviewData> = {}
    for (const file of files) {
      previews[file] = {
        image_data: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
        first_coordinate: { x: 0, y: 0 },
        last_coordinate: { x: 100, y: 100 },
      }
    }
    return HttpResponse.json(previews)
  }),

  http.post('/get_theta_rho_coordinates', async () => {
    // Return mock coordinates for pattern preview
    return HttpResponse.json({
      coordinates: Array.from({ length: 50 }, (_, i) => ({
        theta: i * 7.2,
        rho: 0.5 + Math.sin(i * 0.2) * 0.3,
      })),
    })
  }),

  http.post('/run_theta_rho', async ({ request }) => {
    const body = await request.json() as { file_name?: string; file?: string; pre_execution?: string }
    const file = body.file_name || body.file
    logApiCall('/run_theta_rho', 'POST', body)
    mockData.status.is_running = true
    mockData.status.current_file = file || null
    return HttpResponse.json({ success: true })
  }),

  http.post('/delete_theta_rho_file', async ({ request }) => {
    const body = await request.json() as { file_path: string }
    mockData.patterns = mockData.patterns.filter(p => p.path !== body.file_path)
    return HttpResponse.json({ success: true })
  }),

  http.post('/upload_theta_rho', async () => {
    return HttpResponse.json({ success: true, path: 'patterns/custom/uploaded.thr' })
  }),

  http.get('/api/pattern_history_all', () => {
    return HttpResponse.json({})
  }),

  http.get('/api/pattern_history/:path', () => {
    return HttpResponse.json({ executions: [] })
  }),

  // ----------------
  // Playlist Endpoints
  // ----------------
  http.get('/list_all_playlists', () => {
    return HttpResponse.json(Object.keys(mockData.playlists))
  }),

  http.get('/get_playlist', ({ request }) => {
    const url = new URL(request.url)
    const name = url.searchParams.get('name')
    if (name && mockData.playlists[name]) {
      return HttpResponse.json({ name, files: mockData.playlists[name] })
    }
    return HttpResponse.json({ name: name || '', files: [] })
  }),

  http.post('/create_playlist', async ({ request }) => {
    const body = await request.json() as { name: string; playlist_name?: string; files?: string[] }
    const name = body.playlist_name || body.name
    logApiCall('/create_playlist', 'POST', body)
    mockData.playlists[name] = body.files || []
    return HttpResponse.json({ success: true })
  }),

  http.post('/modify_playlist', async ({ request }) => {
    const body = await request.json() as { name?: string; playlist_name?: string; files: string[] }
    const name = body.playlist_name || body.name || ''
    logApiCall('/modify_playlist', 'POST', body)
    if (mockData.playlists[name]) {
      mockData.playlists[name] = body.files
    }
    return HttpResponse.json({ success: true })
  }),

  http.post('/rename_playlist', async ({ request }) => {
    const body = await request.json() as { old_name: string; new_name: string }
    logApiCall('/rename_playlist', 'POST', body)
    if (mockData.playlists[body.old_name]) {
      mockData.playlists[body.new_name] = mockData.playlists[body.old_name]
      delete mockData.playlists[body.old_name]
    }
    return HttpResponse.json({ success: true })
  }),

  http.delete('/delete_playlist', async ({ request }) => {
    const body = await request.json() as { name?: string; playlist_name?: string }
    const name = body.playlist_name || body.name || ''
    logApiCall('/delete_playlist', 'DELETE', body)
    delete mockData.playlists[name]
    return HttpResponse.json({ success: true })
  }),

  http.post('/run_playlist', async ({ request }) => {
    const body = await request.json() as { name?: string; playlist_name?: string }
    const name = body.playlist_name || body.name || ''
    logApiCall('/run_playlist', 'POST', body)
    const playlist = mockData.playlists[name]
    if (playlist && playlist.length > 0) {
      mockData.status.is_running = true
      mockData.status.playlist_mode = true
      mockData.status.playlist_name = name
      mockData.status.current_file = playlist[0]
      mockData.status.queue = playlist.slice(1)
    }
    return HttpResponse.json({ success: true })
  }),

  http.post('/reorder_playlist', async ({ request }) => {
    const body = await request.json() as { from_index: number; to_index: number }
    // Reorder the current queue
    const queue = [...mockData.status.queue]
    const [item] = queue.splice(body.from_index, 1)
    queue.splice(body.to_index, 0, item)
    mockData.status.queue = queue
    return HttpResponse.json({ success: true })
  }),

  http.post('/add_to_playlist', async ({ request }) => {
    const body = await request.json() as { playlist_name: string; file_path: string }
    if (!mockData.playlists[body.playlist_name]) {
      mockData.playlists[body.playlist_name] = []
    }
    mockData.playlists[body.playlist_name].push(body.file_path)
    return HttpResponse.json({ success: true })
  }),

  http.post('/add_to_queue', async ({ request }) => {
    const body = await request.json() as { file: string; position?: 'next' | 'end' }
    if (body.position === 'next') {
      mockData.status.queue.unshift(body.file)
    } else {
      mockData.status.queue.push(body.file)
    }
    return HttpResponse.json({ success: true })
  }),

  // ----------------
  // Playback Control Endpoints
  // ----------------
  http.post('/pause_execution', () => {
    logApiCall('/pause_execution', 'POST')
    mockData.status.is_paused = true
    return HttpResponse.json({ success: true })
  }),

  http.post('/resume_execution', () => {
    logApiCall('/resume_execution', 'POST')
    mockData.status.is_paused = false
    return HttpResponse.json({ success: true })
  }),

  http.post('/stop_execution', () => {
    logApiCall('/stop_execution', 'POST')
    mockData.status.is_running = false
    mockData.status.is_paused = false
    mockData.status.current_file = null
    mockData.status.playlist_mode = false
    mockData.status.playlist_name = null
    mockData.status.queue = []
    return HttpResponse.json({ success: true })
  }),

  http.post('/force_stop', () => {
    mockData.status.is_running = false
    mockData.status.is_paused = false
    mockData.status.current_file = null
    mockData.status.playlist_mode = false
    mockData.status.queue = []
    return HttpResponse.json({ success: true })
  }),

  http.post('/skip_pattern', () => {
    logApiCall('/skip_pattern', 'POST')
    if (mockData.status.queue.length > 0) {
      mockData.status.current_file = mockData.status.queue.shift() || null
    } else {
      mockData.status.is_running = false
      mockData.status.current_file = null
    }
    return HttpResponse.json({ success: true })
  }),

  http.post('/set_speed', async ({ request }) => {
    const body = await request.json() as { speed: number }
    mockData.status.speed = body.speed
    return HttpResponse.json({ success: true })
  }),

  // ----------------
  // Table Control Endpoints
  // ----------------
  http.post('/send_home', () => {
    mockData.status.theta = 0
    mockData.status.rho = 0
    return HttpResponse.json({ success: true })
  }),

  http.post('/soft_reset', () => {
    return HttpResponse.json({ success: true })
  }),

  http.post('/move_to_center', () => {
    mockData.status.rho = 0
    return HttpResponse.json({ success: true })
  }),

  http.post('/move_to_perimeter', () => {
    mockData.status.rho = 1
    return HttpResponse.json({ success: true })
  }),

  http.post('/send_coordinate', async ({ request }) => {
    const body = await request.json() as { theta: number; rho: number }
    mockData.status.theta = body.theta
    mockData.status.rho = body.rho
    return HttpResponse.json({ success: true })
  }),

  // ----------------
  // Status Endpoints
  // ----------------
  http.get('/serial_status', () => {
    return HttpResponse.json(mockData.status)
  }),

  http.get('/list_serial_ports', () => {
    return HttpResponse.json(['/dev/ttyUSB0', '/dev/ttyUSB1'])
  }),

  // Debug serial endpoints
  http.post('/api/debug-serial/open', () => {
    return HttpResponse.json({ success: true })
  }),

  http.post('/api/debug-serial/close', () => {
    return HttpResponse.json({ success: true })
  }),

  http.post('/api/debug-serial/send', () => {
    return HttpResponse.json({ success: true, response: 'OK' })
  }),
]
