import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach } from 'vitest'
import { setupBrowserMocks, cleanupBrowserMocks } from './mocks/browser'
import { setupMockWebSocket, cleanupMockWebSocket } from './mocks/websocket'
import { server } from './mocks/server'
import { resetMockData } from './mocks/handlers'

// Setup browser mocks FIRST (before MSW starts)
// This ensures WebSocket mock is in place before MSW tries to intercept
beforeAll(() => {
  setupBrowserMocks()
  setupMockWebSocket()
  // Use 'warn' instead of 'error' to avoid failing on WebSocket requests
  // that are handled by our mock WebSocket, not MSW
  server.listen({ onUnhandledRequest: 'warn' })
})

// Reset state between tests
beforeEach(() => {
  resetMockData()
})

// Cleanup after each test
afterEach(() => {
  cleanup()
  server.resetHandlers()
})

// Teardown after all tests
afterAll(() => {
  server.close()
  cleanupMockWebSocket()
  cleanupBrowserMocks()
})
