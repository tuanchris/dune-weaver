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

  socket.onopen = () => {
    if (isStopped) {
      socket.close()
      return
    }
    useStatusStore.setState({ isBackendConnected: true, connectionAttempts: 0 })
    window.dispatchEvent(new CustomEvent('backend-connected'))
  }

  socket.onmessage = (event) => {
    if (isStopped) return
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
    if (isStopped) return
    ws = null
    useStatusStore.setState((prev) => ({
      isBackendConnected: false,
      connectionAttempts: prev.connectionAttempts + 1,
    }))
    reconnectTimeout = setTimeout(connectWebSocket, 3000)
  }

  socket.onerror = () => {
    if (isStopped) return
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
  // Close existing and reconnect
  if (ws) {
    if (ws.readyState === WebSocket.OPEN) ws.close()
    ws = null
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
  if (ws && ws.readyState === WebSocket.OPEN) ws.close()
  ws = null
}
