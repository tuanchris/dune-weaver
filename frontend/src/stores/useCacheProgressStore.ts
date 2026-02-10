import { create } from 'zustand'
import { apiClient } from '@/lib/apiClient'

export interface CacheProgressData {
  is_running: boolean
  stage: string
  processed_files: number
  total_files: number
  current_file: string
  error?: string
}

interface CacheProgressStore {
  cacheProgress: CacheProgressData | null
  isConnected: boolean
  connect: () => void
  disconnect: () => void
}

let ws: WebSocket | null = null

export const useCacheProgressStore = create<CacheProgressStore>()((set, get) => ({
  cacheProgress: null,
  isConnected: false,

  connect: () => {
    // Already connected or connecting
    if (ws) {
      if (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN) return
      ws = null
    }

    const socket = new WebSocket(apiClient.getWebSocketUrl('/ws/cache-progress'))
    ws = socket

    socket.onopen = () => {
      // If disconnect() was called while connecting, close now
      if (ws !== socket) {
        socket.close()
        return
      }
      set({ isConnected: true })
    }

    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        if (message.type === 'cache_progress') {
          const data: CacheProgressData = message.data
          if (data.is_running) {
            set({ cacheProgress: data })
          } else if (data.stage === 'complete') {
            set({ cacheProgress: { ...data } })
            // Auto-disconnect after completion arrives
            setTimeout(() => get().disconnect(), 500)
          } else {
            // Idle — nothing is happening, disconnect
            set({ cacheProgress: null })
            get().disconnect()
          }
        }
      } catch {
        // Ignore parse errors
      }
    }

    socket.onclose = () => {
      if (ws === socket) ws = null
      set({ isConnected: false })
      // No auto-reconnect — Layout will call connect() again if needed
    }

    socket.onerror = () => {
      // Will trigger onclose
    }
  },

  disconnect: () => {
    if (ws) {
      if (ws.readyState === WebSocket.OPEN) ws.close()
      ws = null
    }
    set({ isConnected: false })
  },
}))
