/**
 * Centralized API client for multi-table support.
 *
 * This module provides a single point for all API and WebSocket communications,
 * allowing easy switching between different backend instances.
 */

type RequestMethod = 'GET' | 'POST' | 'PATCH' | 'DELETE' | 'PUT'

interface RequestOptions {
  method?: RequestMethod
  body?: unknown
  headers?: Record<string, string>
  signal?: AbortSignal
}

class ApiClient {
  private _baseUrl: string = ''
  private _listeners: Set<(url: string) => void> = new Set()

  /**
   * Get the current base URL.
   * Empty string means use the current origin (relative URLs).
   */
  get baseUrl(): string {
    return this._baseUrl
  }

  /**
   * Set the base URL for all API requests.
   * @param url - The base URL (e.g., 'http://192.168.1.100:8080') or empty for relative URLs
   */
  setBaseUrl(url: string): void {
    // Remove trailing slash
    const newUrl = url.replace(/\/$/, '')
    // Only notify if the URL actually changed
    if (newUrl === this._baseUrl) return
    this._baseUrl = newUrl
    // Notify listeners
    this._listeners.forEach(listener => listener(this._baseUrl))
  }

  /**
   * Subscribe to base URL changes.
   * @param listener - Callback when base URL changes
   * @returns Unsubscribe function
   */
  onBaseUrlChange(listener: (url: string) => void): () => void {
    this._listeners.add(listener)
    return () => this._listeners.delete(listener)
  }

  /**
   * Build full URL for an endpoint.
   */
  private buildUrl(endpoint: string): string {
    // Ensure endpoint starts with /
    const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`
    return `${this._baseUrl}${path}`
  }

  /**
   * Make an HTTP request.
   */
  async request<T = unknown>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const { method = 'GET', body, headers = {}, signal } = options

    const url = this.buildUrl(endpoint)

    const fetchOptions: RequestInit = {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...headers,
      },
      signal,
    }

    if (body !== undefined) {
      fetchOptions.body = JSON.stringify(body)
    }

    const response = await fetch(url, fetchOptions)

    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`HTTP ${response.status}: ${errorText}`)
    }

    // Handle empty responses
    const text = await response.text()
    if (!text) {
      return {} as T
    }

    return JSON.parse(text) as T
  }

  /**
   * GET request
   */
  async get<T = unknown>(endpoint: string, signal?: AbortSignal): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET', signal })
  }

  /**
   * POST request
   */
  async post<T = unknown>(endpoint: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    return this.request<T>(endpoint, { method: 'POST', body, signal })
  }

  /**
   * PATCH request
   */
  async patch<T = unknown>(endpoint: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    return this.request<T>(endpoint, { method: 'PATCH', body, signal })
  }

  /**
   * DELETE request
   */
  async delete<T = unknown>(endpoint: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    return this.request<T>(endpoint, { method: 'DELETE', body, signal })
  }

  /**
   * Build WebSocket URL for an endpoint.
   */
  getWebSocketUrl(endpoint: string): string {
    // Ensure endpoint starts with /
    const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`

    if (this._baseUrl) {
      // Parse the base URL to get host
      const url = new URL(this._baseUrl)
      const protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
      return `${protocol}//${url.host}${path}`
    } else {
      // Use current page's host for relative URLs
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      // In development mode (Vite on port 5173), connect directly to backend (port 8080)
      // This bypasses Vite's WebSocket proxy which has issues with Safari mobile
      const host = window.location.hostname
      const port = import.meta.env.DEV ? '8080' : window.location.port
      const portSuffix = port ? `:${port}` : ''
      return `${protocol}//${host}${portSuffix}${path}`
    }
  }

  /**
   * Build URL for static assets (like pattern previews).
   */
  getAssetUrl(path: string): string {
    // Ensure path starts with /
    const assetPath = path.startsWith('/') ? path : `/${path}`
    return `${this._baseUrl}${assetPath}`
  }

  /**
   * Upload a file via POST.
   */
  async uploadFile(
    endpoint: string,
    file: File,
    fieldName: string = 'file',
    additionalData?: Record<string, string>
  ): Promise<unknown> {
    const url = this.buildUrl(endpoint)
    const formData = new FormData()
    formData.append(fieldName, file)

    if (additionalData) {
      Object.entries(additionalData).forEach(([key, value]) => {
        formData.append(key, value)
      })
    }

    const response = await fetch(url, {
      method: 'POST',
      body: formData,
      // Don't set Content-Type - let browser set it with boundary
    })

    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`HTTP ${response.status}: ${errorText}`)
    }

    const text = await response.text()
    if (!text) {
      return {}
    }

    return JSON.parse(text)
  }
}

// Export singleton instance
export const apiClient = new ApiClient()

// Pre-initialize base URL from localStorage to avoid race conditions.
// This runs synchronously at module load time, before React renders,
// ensuring WebSocket connections use the correct URL from the start.
function initializeBaseUrlFromStorage(): void {
  try {
    const STORAGE_KEY = 'duneweaver_tables'
    const ACTIVE_TABLE_KEY = 'duneweaver_active_table'

    const stored = localStorage.getItem(STORAGE_KEY)
    const activeId = localStorage.getItem(ACTIVE_TABLE_KEY)

    if (!stored || !activeId) return

    const data = JSON.parse(stored)
    const tables = data.tables || []
    const active = tables.find((t: { id: string }) => t.id === activeId)

    if (!active?.url) return

    // Normalize URL for comparison (handles port differences like :80)
    const normalizeOrigin = (url: string): string => {
      try {
        return new URL(url).origin
      } catch {
        return url
      }
    }

    const normalizedActiveUrl = normalizeOrigin(active.url)
    const currentOrigin = window.location.origin

    // Only set base URL for remote tables (different origin)
    if (normalizedActiveUrl !== currentOrigin) {
      apiClient.setBaseUrl(active.url)
    }
  } catch {
    // Silently fail - TableContext will handle initialization as fallback
  }
}

// Run initialization immediately at module load
initializeBaseUrlFromStorage()

// Export class for testing
export { ApiClient }
