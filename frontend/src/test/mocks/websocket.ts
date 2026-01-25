import { vi } from 'vitest'

type MessageHandler = (event: MessageEvent) => void

export class MockWebSocket {
  static instances: MockWebSocket[] = []

  url: string
  readyState: number = WebSocket.CONNECTING
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onmessage: MessageHandler | null = null
  onerror: ((error: Event) => void) | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)

    // Simulate connection after microtask
    setTimeout(() => {
      this.readyState = WebSocket.OPEN
      this.onopen?.()
    }, 0)
  }

  send(_data: string) {
    // Mock implementation - can be extended to handle specific messages
  }

  close() {
    this.readyState = WebSocket.CLOSED
    this.onclose?.()
  }

  // Helper to simulate receiving a message
  simulateMessage(data: unknown) {
    if (this.onmessage) {
      const event = new MessageEvent('message', {
        data: JSON.stringify(data),
      })
      this.onmessage(event)
    }
  }

  // Helper to simulate connection error
  simulateError() {
    if (this.onerror) {
      this.onerror(new Event('error'))
    }
  }

  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
}

// Install mock WebSocket globally
export function setupMockWebSocket() {
  MockWebSocket.instances = []
  vi.stubGlobal('WebSocket', MockWebSocket)
}

// Get the most recent WebSocket instance
export function getLastWebSocket(): MockWebSocket | undefined {
  return MockWebSocket.instances[MockWebSocket.instances.length - 1]
}

// Clean up mock WebSocket
export function cleanupMockWebSocket() {
  MockWebSocket.instances.forEach(ws => ws.close())
  MockWebSocket.instances = []
  vi.unstubAllGlobals()
}
