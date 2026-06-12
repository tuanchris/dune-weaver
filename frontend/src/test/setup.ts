import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach } from 'vitest'
import { setupBrowserMocks, cleanupBrowserMocks } from './mocks/browser'
import { setupMockWebSocket, cleanupMockWebSocket } from './mocks/websocket'
import { server } from './mocks/server'
import { resetMockData, resetApiCallLog } from './mocks/handlers'
import { apiClient } from '@/lib/apiClient'

// Stub WebSocket at MODULE scope, not in beforeAll: useStatusStore opens its
// socket at import time, which happens before beforeAll runs. Node's native
// WebSocket would otherwise connect to a real dev backend on this machine
// (if one is running) and its live status pushes would clobber seeded test
// state — making the suite pass or fail depending on what's running locally.
setupMockWebSocket()

// Setup browser mocks FIRST (before MSW starts)
// This ensures WebSocket mock is in place before MSW tries to intercept
beforeAll(() => {
  setupBrowserMocks()
  // Use 'warn' instead of 'error' to avoid failing on WebSocket requests
  // that are handled by our mock WebSocket, not MSW
  server.listen({ onUnhandledRequest: 'warn' })
})

// Reset state between tests
beforeEach(() => {
  resetMockData()
  resetApiCallLog()
  // Cross-test pollution guards: TableContext persists tables/active-id to
  // localStorage, and apiClient's base URL is module state. A leftover base
  // URL makes TableProvider call setBaseUrl on a later mount, which fires
  // onBaseUrlChange and wipes the status store mid-test (seeded statuses
  // vanish, connection-gated buttons disable). Reset both up front — this
  // runs before each file's own beforeEach, so seeds applied there survive.
  localStorage.clear()
  apiClient.setBaseUrl('')
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
