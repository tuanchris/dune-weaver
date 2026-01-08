import { Outlet, Link, useLocation } from 'react-router-dom'
import { useEffect, useState, useRef } from 'react'
import { toast } from 'sonner'
import { NowPlayingBar } from '@/components/NowPlayingBar'

const navItems = [
  { path: '/', label: 'Browse', icon: 'grid_view', title: 'Browse Patterns' },
  { path: '/playlists', label: 'Playlists', icon: 'playlist_play', title: 'Playlists' },
  { path: '/table-control', label: 'Control', icon: 'tune', title: 'Table Control' },
  { path: '/led', label: 'LED', icon: 'lightbulb', title: 'LED Control' },
  { path: '/settings', label: 'Settings', icon: 'settings', title: 'Settings' },
]

const DEFAULT_APP_NAME = 'Dune Weaver'

export function Layout() {
  const location = useLocation()
  const [isDark, setIsDark] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('theme')
      if (saved) return saved === 'dark'
      return window.matchMedia('(prefers-color-scheme: dark)').matches
    }
    return false
  })

  // App customization
  const [appName, setAppName] = useState(DEFAULT_APP_NAME)
  const [customLogo, setCustomLogo] = useState<string | null>(null)

  // Connection status
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  // Fetch app settings
  const fetchAppSettings = () => {
    fetch('/api/settings')
      .then((r) => r.json())
      .then((settings) => {
        if (settings.app?.name) {
          setAppName(settings.app.name)
        } else {
          setAppName(DEFAULT_APP_NAME)
        }
        setCustomLogo(settings.app?.custom_logo || null)
      })
      .catch(() => {})
  }

  useEffect(() => {
    fetchAppSettings()

    // Listen for branding updates from Settings page
    const handleBrandingUpdate = () => {
      fetchAppSettings()
    }
    window.addEventListener('branding-updated', handleBrandingUpdate)

    return () => {
      window.removeEventListener('branding-updated', handleBrandingUpdate)
    }
  }, [])

  // Logs drawer state
  const [isLogsOpen, setIsLogsOpen] = useState(false)

  // Now Playing bar state
  const [isNowPlayingOpen, setIsNowPlayingOpen] = useState(false)
  const [logs, setLogs] = useState<Array<{ timestamp: string; level: string; logger: string; message: string }>>([])
  const [logLevelFilter, setLogLevelFilter] = useState<string>('ALL')
  const logsWsRef = useRef<WebSocket | null>(null)
  const logsContainerRef = useRef<HTMLDivElement>(null)

  // Check device connection status via WebSocket
  useEffect(() => {
    const connectWebSocket = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws/status`)

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          // Use device connection status from the status message
          if (data.connected !== undefined) {
            setIsConnected(data.connected)
          }
        } catch {
          // Ignore parse errors
        }
      }

      ws.onclose = () => {
        // Reconnect after 3 seconds (don't change device status on WS disconnect)
        setTimeout(connectWebSocket, 3000)
      }

      wsRef.current = ws
    }

    connectWebSocket()

    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [])

  // Connect to logs WebSocket when drawer opens
  useEffect(() => {
    if (!isLogsOpen) {
      // Close WebSocket when drawer closes
      if (logsWsRef.current) {
        logsWsRef.current.close()
        logsWsRef.current = null
      }
      return
    }

    // Fetch initial logs
    const fetchInitialLogs = async () => {
      try {
        const response = await fetch('/api/logs?limit=200')
        const data = await response.json()
        // Filter out empty/invalid log entries
        const validLogs = (data.logs || []).filter(
          (log: { message?: string }) => log && log.message && log.message.trim() !== ''
        )
        // API returns newest first, reverse to show oldest first (newest at bottom)
        setLogs(validLogs.reverse())
        // Scroll to bottom after initial load
        setTimeout(() => {
          if (logsContainerRef.current) {
            logsContainerRef.current.scrollTop = logsContainerRef.current.scrollHeight
          }
        }, 100)
      } catch {
        // Ignore errors
      }
    }

    fetchInitialLogs()

    // Connect to WebSocket for real-time updates
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null

    const connectLogsWebSocket = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws/logs`)

      ws.onopen = () => {
        console.log('Logs WebSocket connected')
      }

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)

          // Skip heartbeat messages
          if (message.type === 'heartbeat') {
            return
          }

          // Extract log from wrapped structure
          const log = message.type === 'log_entry' ? message.data : message

          // Skip empty or invalid log entries
          if (!log || !log.message || log.message.trim() === '') {
            return
          }
          setLogs((prev) => {
            const newLogs = [...prev, log]
            // Keep only last 500 logs to prevent memory issues
            if (newLogs.length > 500) {
              return newLogs.slice(-500)
            }
            return newLogs
          })
          // Auto-scroll to bottom
          setTimeout(() => {
            if (logsContainerRef.current) {
              logsContainerRef.current.scrollTop = logsContainerRef.current.scrollHeight
            }
          }, 10)
        } catch {
          // Ignore parse errors
        }
      }

      ws.onclose = () => {
        console.log('Logs WebSocket closed, reconnecting...')
        // Reconnect after 3 seconds if drawer is still open
        reconnectTimeout = setTimeout(() => {
          if (logsWsRef.current === ws) {
            connectLogsWebSocket()
          }
        }, 3000)
      }

      ws.onerror = (error) => {
        console.error('Logs WebSocket error:', error)
      }

      logsWsRef.current = ws
    }

    connectLogsWebSocket()

    return () => {
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout)
      }
      if (logsWsRef.current) {
        logsWsRef.current.close()
        logsWsRef.current = null
      }
    }
  }, [isLogsOpen])

  const handleOpenLogs = () => {
    setIsLogsOpen(true)
  }

  // Filter logs by level
  const filteredLogs = logLevelFilter === 'ALL'
    ? logs
    : logs.filter((log) => log.level === logLevelFilter)

  // Format timestamp safely
  const formatTimestamp = (timestamp: string) => {
    if (!timestamp) return '--:--:--'
    try {
      const date = new Date(timestamp)
      if (isNaN(date.getTime())) return '--:--:--'
      return date.toLocaleTimeString()
    } catch {
      return '--:--:--'
    }
  }

  // Copy logs to clipboard
  const handleCopyLogs = () => {
    const text = filteredLogs
      .map((log) => `${formatTimestamp(log.timestamp)} [${log.level}] ${log.message}`)
      .join('\n')
    navigator.clipboard.writeText(text)
    toast.success('Logs copied to clipboard')
  }

  // Download logs as file
  const handleDownloadLogs = () => {
    const text = filteredLogs
      .map((log) => `${log.timestamp} [${log.level}] [${log.logger}] ${log.message}`)
      .join('\n')
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `dune-weaver-logs-${new Date().toISOString().split('T')[0]}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleRestart = async () => {
    if (!confirm('Are you sure you want to restart the system?')) return

    try {
      const response = await fetch('/restart', { method: 'POST' })
      if (response.ok) {
        toast.success('System is restarting...')
      } else {
        throw new Error('Restart failed')
      }
    } catch {
      toast.error('Failed to restart system')
    }
  }

  // Update document title based on current page
  useEffect(() => {
    const currentNav = navItems.find((item) => item.path === location.pathname)
    if (currentNav) {
      document.title = `${currentNav.title} | ${appName}`
    } else {
      document.title = appName
    }
  }, [location.pathname, appName])

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark')
      localStorage.setItem('theme', 'dark')
    } else {
      document.documentElement.classList.remove('dark')
      localStorage.setItem('theme', 'light')
    }
  }, [isDark])

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-40 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="flex h-14 items-center justify-between px-4">
          <Link to="/" className="flex items-center gap-2">
            <img
              src={customLogo ? `/static/custom/${customLogo}` : '/static/android-chrome-192x192.png'}
              alt={appName}
              className="w-8 h-8 rounded-full object-cover"
            />
            <span className="font-semibold text-lg">{appName}</span>
            <span
              className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}
              title={isConnected ? 'Connected' : 'Disconnected'}
            />
          </Link>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setIsNowPlayingOpen(!isNowPlayingOpen)}
              className={`rounded-full w-10 h-10 flex items-center justify-center hover:bg-accent ${
                isNowPlayingOpen ? 'text-primary' : ''
              }`}
              aria-label="Now playing"
              title="Now Playing"
            >
              <span className="material-icons-outlined">play_circle</span>
            </button>
            <button
              onClick={handleOpenLogs}
              className="rounded-full w-10 h-10 flex items-center justify-center hover:bg-accent"
              aria-label="View logs"
              title="View Application Logs"
            >
              <span className="material-icons-outlined">article</span>
            </button>
            <button
              onClick={handleRestart}
              className="rounded-full w-10 h-10 flex items-center justify-center hover:bg-accent hover:text-amber-500"
              aria-label="Restart system"
              title="Restart System"
            >
              <span className="material-icons-outlined">restart_alt</span>
            </button>
            <button
              onClick={() => setIsDark(!isDark)}
              className="rounded-full w-10 h-10 flex items-center justify-center hover:bg-accent"
              aria-label="Toggle dark mode"
            >
              <span className="material-icons-outlined">
                {isDark ? 'light_mode' : 'dark_mode'}
              </span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className={`container mx-auto px-4 transition-all duration-300 ${isLogsOpen ? 'pb-80' : 'pb-20'}`}>
        <Outlet />
      </main>

      {/* Now Playing Bar */}
      <NowPlayingBar
        isLogsOpen={isLogsOpen}
        isVisible={isNowPlayingOpen}
        onClose={() => setIsNowPlayingOpen(false)}
      />

      {/* Logs Drawer */}
      <div
        className={`fixed left-0 right-0 z-30 bg-background border-t border-border transition-all duration-300 ${
          isLogsOpen ? 'bottom-16 h-64' : 'bottom-16 h-0'
        }`}
      >
        {isLogsOpen && (
          <>
            <div className="flex items-center justify-between px-4 py-2 border-b bg-muted/50">
              <div className="flex items-center gap-3">
                <h2 className="text-sm font-semibold">Logs</h2>
                <select
                  value={logLevelFilter}
                  onChange={(e) => setLogLevelFilter(e.target.value)}
                  className="text-xs bg-background border rounded px-2 py-1"
                >
                  <option value="ALL">All Levels</option>
                  <option value="DEBUG">Debug</option>
                  <option value="INFO">Info</option>
                  <option value="WARNING">Warning</option>
                  <option value="ERROR">Error</option>
                </select>
                <span className="text-xs text-muted-foreground">
                  {filteredLogs.length} entries
                </span>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={handleCopyLogs}
                  className="rounded-full w-7 h-7 flex items-center justify-center hover:bg-accent"
                  title="Copy logs"
                >
                  <span className="material-icons-outlined text-base">content_copy</span>
                </button>
                <button
                  onClick={handleDownloadLogs}
                  className="rounded-full w-7 h-7 flex items-center justify-center hover:bg-accent"
                  title="Download logs"
                >
                  <span className="material-icons-outlined text-base">download</span>
                </button>
                <button
                  onClick={() => setIsLogsOpen(false)}
                  className="rounded-full w-7 h-7 flex items-center justify-center hover:bg-accent"
                  title="Close logs"
                >
                  <span className="material-icons-outlined text-base">close</span>
                </button>
              </div>
            </div>
            <div
              ref={logsContainerRef}
              className="h-[calc(100%-40px)] overflow-auto overscroll-contain p-3 font-mono text-xs space-y-0.5"
            >
              {filteredLogs.length > 0 ? (
                filteredLogs.map((log, i) => (
                  <div key={i} className="py-0.5 flex gap-2">
                    <span className="text-muted-foreground shrink-0">
                      {formatTimestamp(log.timestamp)}
                    </span>
                    <span className={`shrink-0 font-semibold ${
                      log.level === 'ERROR' ? 'text-red-500' :
                      log.level === 'WARNING' ? 'text-amber-500' :
                      log.level === 'DEBUG' ? 'text-muted-foreground' :
                      'text-foreground'
                    }`}>
                      [{log.level || 'LOG'}]
                    </span>
                    <span className="break-all">{log.message || ''}</span>
                  </div>
                ))
              ) : (
                <p className="text-muted-foreground text-center py-4">No logs available</p>
              )}
            </div>
          </>
        )}
      </div>

      {/* Bottom Navigation */}
      <nav className="fixed bottom-0 left-0 right-0 z-40 border-t border-border bg-background">
        <div className="max-w-5xl mx-auto grid grid-cols-5 h-16">
          {navItems.map((item) => {
            const isActive = location.pathname === item.path
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex flex-col items-center justify-center gap-1 transition-colors ${
                  isActive
                    ? 'text-primary'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <span className="material-icons-outlined text-xl">
                  {item.icon}
                </span>
                <span className="text-xs font-medium">{item.label}</span>
              </Link>
            )
          })}
        </div>
      </nav>
    </div>
  )
}
