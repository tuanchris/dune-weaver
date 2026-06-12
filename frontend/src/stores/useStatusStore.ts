import { create } from 'zustand'
import { apiClient } from '@/lib/apiClient'

export interface StatusData {
  current_file: string | null
  is_paused: boolean
  manual_pause: boolean
  scheduled_pause: boolean
  is_running: boolean
  is_homing: boolean
  is_clearing: boolean
  sensor_homing_failed: boolean
  progress: {
    current: number
    total: number
    remaining_time: number | null
    elapsed_time: number
    percentage: number
    last_completed_time?: {
      actual_time_seconds: number
      actual_time_formatted: string
      timestamp: string
    }
  } | null
  playlist: {
    current_index: number
    total_files: number
    mode: string
    next_file: string | null
    files: string[]
    name: string | null
  } | null
  speed: number
  pause_time_remaining: number
  original_pause_time: number | null
  connection_status: boolean
  current_theta: number
  current_rho: number
  firmware_version: string | null
  table_type: string | null
}

interface StatusStore {
  isBackendConnected: boolean
  connectionAttempts: number
  status: StatusData | null
}

export const useStatusStore = create<StatusStore>()(() => ({
  isBackendConnected: false,
  connectionAttempts: 0,
  status: null,
}))

// --- Module-level WebSocket lifecycle (singleton, outside React) ---

let ws: WebSocket | null = null
let reconnectTimeout: ReturnType<typeof setTimeout> | null = null
let isStopped = false

function connectWebSocket() {
  if (isStopped) return

  // Don't interrupt an existing connection that's still connecting
  if (ws) {
    if (ws.readyState === WebSocket.CONNECTING) return
    if (ws.readyState === WebSocket.OPEN) ws.close()
    ws = null
  }

  const socket = new WebSocket(apiClient.getWebSocketUrl('/ws/status'))
  ws = socket

  // Every handler checks `ws === socket` so a socket orphaned by a table
  // switch (including one still CONNECTING when the switch happened) can
  // never update the store on behalf of the new connection
  socket.onopen = () => {
    if (isStopped || ws !== socket) {
      socket.close()
      return
    }
    useStatusStore.setState({ isBackendConnected: true, connectionAttempts: 0 })
    window.dispatchEvent(new CustomEvent('backend-connected'))
  }

  socket.onmessage = (event) => {
    if (isStopped || ws !== socket) return
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'status_update' && data.data) {
        useStatusStore.setState({ status: data.data })
      }
    } catch {
      // Ignore parse errors
    }
  }

  socket.onclose = () => {
    if (isStopped || ws !== socket) return
    ws = null
    const attempts = useStatusStore.getState().connectionAttempts + 1
    useStatusStore.setState({
      isBackendConnected: false,
      connectionAttempts: attempts,
    })
    // Exponential backoff with jitter, capped at 30s — a flat interval makes
    // every open tab hammer the backend in lockstep while it's down
    const delay =
      Math.min(30_000, 3_000 * 2 ** Math.min(attempts - 1, 4)) + Math.random() * 1_000
    reconnectTimeout = setTimeout(connectWebSocket, delay)
  }

  socket.onerror = () => {
    if (isStopped || ws !== socket) return
    useStatusStore.setState({ isBackendConnected: false })
  }
}

// Reconnect on table switch
apiClient.onBaseUrlChange(() => {
  useStatusStore.setState({ status: null, isBackendConnected: false })
  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout)
    reconnectTimeout = null
  }
  // Close existing and reconnect. Null the ref first so the old socket's
  // handlers see ws !== socket and stand down; close() is valid (and
  // necessary) even on a socket still in CONNECTING state.
  if (ws) {
    const oldSocket = ws
    ws = null
    oldSocket.close()
  }
  connectWebSocket()
})

// Start connection immediately at module load
connectWebSocket()

// --- Playback transition detection ---

let wasPlaying: boolean | null = null

useStatusStore.subscribe((state) => {
  const s = state.status
  if (!s) return

  const isPlaying =
    Boolean(s.current_file) ||
    Boolean(s.is_running) ||
    Boolean(s.is_paused) ||
    (s.pause_time_remaining ?? 0) > 0

  // Skip first message (page refresh) - only react to transitions
  if (wasPlaying !== null) {
    if (isPlaying && !wasPlaying) {
      window.dispatchEvent(new CustomEvent('playback-started'))
    }
  }
  wasPlaying = isPlaying
})

// Reset wasPlaying on table switch so we don't fire false transitions
apiClient.onBaseUrlChange(() => {
  wasPlaying = null
})

// For HMR / cleanup in tests
export function _stopStatusWebSocket() {
  isStopped = true
  if (reconnectTimeout) clearTimeout(reconnectTimeout)
  // close() is safe in any readyState, including CONNECTING
  ws?.close()
  ws = null
}
