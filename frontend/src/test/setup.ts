import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach } from 'vitest'
import { server } from './mocks/server'
import { resetMockData } from './mocks/handlers'
import { setupBrowserMocks, cleanupBrowserMocks } from './mocks/browser'
import { setupMockWebSocket, cleanupMockWebSocket } from './mocks/websocket'

// Setup browser mocks
beforeAll(() => {
  setupBrowserMocks()
  setupMockWebSocket()
  server.listen({ onUnhandledRequest: 'error' })
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
