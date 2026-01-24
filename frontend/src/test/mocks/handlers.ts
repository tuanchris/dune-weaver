import { http, HttpResponse } from 'msw'

// Default mock data
const mockPatterns = [
  { name: 'star.thr', path: 'patterns/star.thr' },
  { name: 'spiral.thr', path: 'patterns/spiral.thr' },
]

const mockPlaylists = ['default', 'favorites']

const mockStatus = {
  is_running: false,
  is_paused: false,
  current_file: null,
  speed: 100,
  connection_status: 'connected',
}

export const handlers = [
  // Pattern endpoints
  http.get('/list_theta_rho_files', () => {
    return HttpResponse.json(mockPatterns)
  }),

  http.get('/list_theta_rho_files_with_metadata', () => {
    return HttpResponse.json(mockPatterns.map(p => ({ ...p, metadata: {} })))
  }),

  // Playlist endpoints
  http.get('/list_all_playlists', () => {
    return HttpResponse.json(mockPlaylists)
  }),

  // Status endpoint
  http.get('/serial_status', () => {
    return HttpResponse.json(mockStatus)
  }),

  // API prefix versions
  http.get('/api/patterns', () => {
    return HttpResponse.json(mockPatterns)
  }),

  http.get('/api/status', () => {
    return HttpResponse.json(mockStatus)
  }),
]
