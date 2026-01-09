import { Outlet, Link, useLocation } from 'react-router-dom'
import { useEffect, useState, useRef } from 'react'
import { toast } from 'sonner'
import { NowPlayingBar } from '@/components/NowPlayingBar'
import { Button } from '@/components/ui/button'

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
  const [isBackendConnected, setIsBackendConnected] = useState(false)
  const [connectionAttempts, setConnectionAttempts] = useState(0)
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
  const [openNowPlayingExpanded, setOpenNowPlayingExpanded] = useState(false)
  const wasPlayingRef = useRef<boolean | null>(null) // Track previous playing state (null = first message)
  const [logs, setLogs] = useState<Array<{ timestamp: string; level: string; logger: string; message: string }>>([])
  const [logLevelFilter, setLogLevelFilter] = useState<string>('ALL')
  const logsWsRef = useRef<WebSocket | null>(null)
  const logsContainerRef = useRef<HTMLDivElement>(null)

  // Check device connection status via WebSocket
  useEffect(() => {
    const connectWebSocket = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws/status`)

      ws.onopen = () => {
        setIsBackendConnected(true)
        setConnectionAttempts(0)
        // Dispatch event so pages can refetch data
        window.dispatchEvent(new CustomEvent('backend-connected'))
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          // Handle status updates
          if (data.type === 'status_update' && data.data) {
            // Update device connection status from the status message
            if (data.data.connection_status !== undefined) {
              setIsConnected(data.data.connection_status)
            }
            // Auto-open/close Now Playing bar based on playback state
            const isPlaying = data.data.is_running || data.data.is_paused
            // Skip auto-open on first message (page refresh) - only react to state changes
            if (wasPlayingRef.current !== null) {
              if (isPlaying && !wasPlayingRef.current) {
                // Playback just started - open the Now Playing bar in expanded mode
                setIsNowPlayingOpen(true)
                setOpenNowPlayingExpanded(true)
                // Close the logs drawer if open
                setIsLogsOpen(false)
                // Reset the expanded flag after a short delay
                setTimeout(() => setOpenNowPlayingExpanded(false), 500)
                // Dispatch event so pages can close their sidebars/panels
                window.dispatchEvent(new CustomEvent('playback-started'))
              } else if (!isPlaying && wasPlayingRef.current) {
                // Playback just stopped - close the Now Playing bar
                setIsNowPlayingOpen(false)
              }
            }
            wasPlayingRef.current = isPlaying
          }
        } catch {
          // Ignore parse errors
        }
      }

      ws.onclose = () => {
        setIsBackendConnected(false)
        setConnectionAttempts((prev) => prev + 1)
        // Reconnect after 3 seconds (don't change device status on WS disconnect)
        setTimeout(connectWebSocket, 3000)
      }

      ws.onerror = () => {
        setIsBackendConnected(false)
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

  const handleShutdown = async () => {
    if (!confirm('Are you sure you want to shutdown the system?')) return

    try {
      const response = await fetch('/shutdown', { method: 'POST' })
      if (response.ok) {
        toast.success('System is shutting down...')
      } else {
        throw new Error('Shutdown failed')
      }
    } catch {
      toast.error('Failed to shutdown system')
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

  // Blocking overlay logs state - shows connection attempts
  const [connectionLogs, setConnectionLogs] = useState<Array<{ timestamp: string; level: string; message: string }>>([])
  const blockingLogsRef = useRef<HTMLDivElement>(null)

  // Cache progress state
  const [cacheProgress, setCacheProgress] = useState<{
    is_running: boolean
    stage: string
    processed_files: number
    total_files: number
    current_file: string
    error?: string
  } | null>(null)
  const cacheWsRef = useRef<WebSocket | null>(null)

  // Cache All Previews prompt state
  const [showCacheAllPrompt, setShowCacheAllPrompt] = useState(false)
  const [cacheAllProgress, setCacheAllProgress] = useState<{
    inProgress: boolean
    completed: number
    total: number
    done: boolean
  } | null>(null)

  // Add connection attempt logs when backend is disconnected
  useEffect(() => {
    if (isBackendConnected) {
      setConnectionLogs([])
      return
    }

    // Add initial log entry
    const addLog = (level: string, message: string) => {
      setConnectionLogs((prev) => {
        const newLog = {
          timestamp: new Date().toISOString(),
          level,
          message,
        }
        const newLogs = [...prev, newLog].slice(-50) // Keep last 50 entries
        return newLogs
      })
      // Auto-scroll to bottom
      setTimeout(() => {
        if (blockingLogsRef.current) {
          blockingLogsRef.current.scrollTop = blockingLogsRef.current.scrollHeight
        }
      }, 10)
    }

    addLog('INFO', `Attempting to connect to backend at ${window.location.host}...`)

    // Log connection attempts
    const interval = setInterval(() => {
      addLog('INFO', `Retrying connection to WebSocket /ws/status...`)

      // Also try HTTP to see if backend is partially up
      fetch('/api/settings', { method: 'GET' })
        .then(() => {
          addLog('INFO', 'HTTP endpoint responding, waiting for WebSocket...')
        })
        .catch(() => {
          // Still down
        })
    }, 3000)

    return () => clearInterval(interval)
  }, [isBackendConnected])

  // Cache progress WebSocket connection
  useEffect(() => {
    if (!isBackendConnected) return

    // Check initial cache progress
    const checkCacheProgress = () => {
      fetch('/cache-progress')
        .then((r) => r.json())
        .then((data) => {
          if (data.is_running) {
            setCacheProgress(data)
            connectCacheWebSocket()
          } else if (data.stage === 'complete' || !data.is_running) {
            setCacheProgress(null)
          }
        })
        .catch(() => {})
    }

    const connectCacheWebSocket = () => {
      if (cacheWsRef.current) return

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws/cache-progress`)

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          if (message.type === 'cache_progress') {
            const data = message.data
            if (!data.is_running && (data.stage === 'complete' || data.stage === 'error')) {
              setCacheProgress(null)
              ws.close()
              cacheWsRef.current = null
              // Show cache all prompt if not already shown
              if (data.stage === 'complete') {
                const promptShown = localStorage.getItem('cacheAllPromptShown')
                if (!promptShown) {
                  setTimeout(() => setShowCacheAllPrompt(true), 500)
                }
              }
            } else {
              setCacheProgress(data)
            }
          }
        } catch {
          // Ignore parse errors
        }
      }

      ws.onclose = () => {
        cacheWsRef.current = null
      }

      ws.onerror = () => {
        // Fallback to polling
        const pollInterval = setInterval(() => {
          fetch('/cache-progress')
            .then((r) => r.json())
            .then((data) => {
              if (!data.is_running) {
                setCacheProgress(null)
                clearInterval(pollInterval)
              } else {
                setCacheProgress(data)
              }
            })
            .catch(() => {})
        }, 1000)
      }

      cacheWsRef.current = ws
    }

    checkCacheProgress()

    return () => {
      if (cacheWsRef.current) {
        cacheWsRef.current.close()
        cacheWsRef.current = null
      }
    }
  }, [isBackendConnected])

  // Calculate cache progress percentage
  const cachePercentage = cacheProgress?.total_files
    ? Math.round((cacheProgress.processed_files / cacheProgress.total_files) * 100)
    : 0

  const getCacheStageText = () => {
    if (!cacheProgress) return ''
    switch (cacheProgress.stage) {
      case 'starting':
        return 'Initializing...'
      case 'metadata':
        return 'Processing pattern metadata'
      case 'images':
        return 'Generating pattern previews'
      default:
        return 'Processing...'
    }
  }

  // Cache all previews in browser
  const handleCacheAllPreviews = async () => {
    setCacheAllProgress({ inProgress: true, completed: 0, total: 0, done: false })

    try {
      // Fetch all patterns
      const response = await fetch('/api/patterns')
      const data = await response.json()
      const patterns = data.patterns || []

      setCacheAllProgress({ inProgress: true, completed: 0, total: patterns.length, done: false })

      // Process in batches of 5
      const batchSize = 5
      let completed = 0

      for (let i = 0; i < patterns.length; i += batchSize) {
        const batch = patterns.slice(i, i + batchSize)

        const batchPromises = batch.map(async (pattern: { file: string }) => {
          try {
            // Fetch preview URL
            const previewResponse = await fetch(
              `/api/pattern/${encodeURIComponent(pattern.file)}/preview`
            )
            if (previewResponse.ok) {
              const previewData = await previewResponse.json()
              if (previewData.preview_url) {
                // Pre-load image to cache it
                return new Promise<void>((resolve) => {
                  const img = new Image()
                  img.onload = () => resolve()
                  img.onerror = () => resolve()
                  img.src = previewData.preview_url
                })
              }
            }
          } catch {
            // Continue even if one fails
          }
        })

        await Promise.all(batchPromises)
        completed += batch.length
        setCacheAllProgress({ inProgress: true, completed, total: patterns.length, done: false })

        // Small delay between batches
        if (i + batchSize < patterns.length) {
          await new Promise((resolve) => setTimeout(resolve, 100))
        }
      }

      setCacheAllProgress({ inProgress: false, completed: patterns.length, total: patterns.length, done: true })
    } catch (error) {
      console.error('Error caching previews:', error)
      setCacheAllProgress(null)
      toast.error('Failed to cache previews')
    }
  }

  const handleSkipCacheAll = () => {
    localStorage.setItem('cacheAllPromptShown', 'true')
    setShowCacheAllPrompt(false)
    setCacheAllProgress(null)
  }

  const handleCloseCacheAllDone = () => {
    localStorage.setItem('cacheAllPromptShown', 'true')
    setShowCacheAllPrompt(false)
    setCacheAllProgress(null)
  }

  const cacheAllPercentage = cacheAllProgress?.total
    ? Math.round((cacheAllProgress.completed / cacheAllProgress.total) * 100)
    : 0

  return (
    <div className="min-h-screen bg-background">
      {/* Cache Progress Blocking Overlay */}
      {cacheProgress?.is_running && (
        <div className="fixed inset-0 z-50 bg-background/95 backdrop-blur-sm flex flex-col items-center justify-center p-4">
          <div className="w-full max-w-md space-y-6">
            <div className="text-center space-y-4">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mb-2">
                <span className="material-icons-outlined text-4xl text-primary animate-pulse">
                  cached
                </span>
              </div>
              <h2 className="text-2xl font-bold">Initializing Pattern Cache</h2>
              <p className="text-muted-foreground">
                Preparing your pattern previews...
              </p>
            </div>

            {/* Progress Bar */}
            <div className="space-y-2">
              <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                <div
                  className="bg-primary h-2 rounded-full transition-all duration-300"
                  style={{ width: `${cachePercentage}%` }}
                />
              </div>
              <div className="flex justify-between text-sm text-muted-foreground">
                <span>
                  {cacheProgress.processed_files} of {cacheProgress.total_files} patterns
                </span>
                <span>{cachePercentage}%</span>
              </div>
            </div>

            {/* Stage Info */}
            <div className="text-center space-y-1">
              <p className="text-sm font-medium">{getCacheStageText()}</p>
              {cacheProgress.current_file && (
                <p className="text-xs text-muted-foreground truncate max-w-full">
                  {cacheProgress.current_file}
                </p>
              )}
            </div>

            {/* Hint */}
            <p className="text-center text-xs text-muted-foreground">
              This only happens once after updates or when new patterns are added
            </p>
          </div>
        </div>
      )}

      {/* Cache All Previews Prompt Modal */}
      {showCacheAllPrompt && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-background rounded-lg shadow-xl w-full max-w-md">
            <div className="p-6">
              <div className="text-center space-y-4">
                <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-primary/10 mb-2">
                  <span className="material-icons-outlined text-2xl text-primary">
                    download_for_offline
                  </span>
                </div>
                <h2 className="text-xl font-semibold">Cache All Pattern Previews?</h2>
                <p className="text-muted-foreground text-sm">
                  Would you like to cache all pattern previews for faster browsing? This will download and store preview images in your browser for instant loading.
                </p>

                <div className="bg-amber-500/10 border border-amber-500/20 p-3 rounded-lg text-sm">
                  <p className="text-amber-600 dark:text-amber-400">
                    <strong>Note:</strong> This cache is browser-specific. You'll need to repeat this for each browser you use.
                  </p>
                </div>

                {/* Progress section */}
                {cacheAllProgress?.inProgress && (
                  <div className="space-y-2">
                    <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                      <div
                        className="bg-primary h-2 rounded-full transition-all duration-300"
                        style={{ width: `${cacheAllPercentage}%` }}
                      />
                    </div>
                    <div className="flex justify-between text-sm text-muted-foreground">
                      <span>
                        {cacheAllProgress.completed} of {cacheAllProgress.total} previews
                      </span>
                      <span>{cacheAllPercentage}%</span>
                    </div>
                  </div>
                )}

                {/* Completion message */}
                {cacheAllProgress?.done && (
                  <div className="space-y-4">
                    <p className="text-green-600 dark:text-green-400 flex items-center justify-center gap-2">
                      <span className="material-icons text-base">check_circle</span>
                      All previews cached successfully!
                    </p>
                    <Button onClick={handleCloseCacheAllDone} className="w-full">
                      Done
                    </Button>
                  </div>
                )}

                {/* Buttons (hidden during progress or after completion) */}
                {!cacheAllProgress && (
                  <div className="flex gap-3 justify-center">
                    <Button variant="ghost" onClick={handleSkipCacheAll}>
                      Skip for now
                    </Button>
                    <Button onClick={handleCacheAllPreviews}>
                      Cache All Previews
                    </Button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Backend Connection Blocking Overlay */}
      {!isBackendConnected && (
        <div className="fixed inset-0 z-50 bg-background/95 backdrop-blur-sm flex flex-col items-center justify-center p-4">
          <div className="w-full max-w-2xl space-y-6">
            {/* Connection Status */}
            <div className="text-center space-y-4">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-amber-500/10 mb-2">
                <span className="material-icons-outlined text-4xl text-amber-500 animate-pulse">
                  sync
                </span>
              </div>
              <h2 className="text-2xl font-bold">Connecting to Backend</h2>
              <p className="text-muted-foreground">
                {connectionAttempts === 0
                  ? 'Establishing connection...'
                  : `Reconnecting... (attempt ${connectionAttempts})`
                }
              </p>
              <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
                <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
                <span>Waiting for server at {window.location.host}</span>
              </div>
            </div>

            {/* Connection Logs Panel */}
            <div className="bg-muted/50 rounded-lg border overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2 border-b bg-muted">
                <div className="flex items-center gap-2">
                  <span className="material-icons-outlined text-base">terminal</span>
                  <span className="text-sm font-medium">Connection Log</span>
                </div>
                <span className="text-xs text-muted-foreground">
                  {connectionLogs.length} entries
                </span>
              </div>
              <div
                ref={blockingLogsRef}
                className="h-48 overflow-auto p-3 font-mono text-xs space-y-0.5"
              >
                {connectionLogs.map((log, i) => (
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
                      [{log.level}]
                    </span>
                    <span className="break-all">{log.message}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Hint */}
            <p className="text-center text-xs text-muted-foreground">
              Make sure the backend server is running on port 8080
            </p>
          </div>
        </div>
      )}

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
              className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}
              title={isConnected ? 'Connected to table' : 'Disconnected from table'}
            />
          </Link>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setIsDark(!isDark)}
              className="rounded-full"
              aria-label="Toggle dark mode"
              title="Toggle Theme"
            >
              <span className="material-icons-outlined">
                {isDark ? 'light_mode' : 'dark_mode'}
              </span>
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleOpenLogs}
              className="rounded-full"
              aria-label="View logs"
              title="View Application Logs"
            >
              <span className="material-icons-outlined">article</span>
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleRestart}
              className="rounded-full text-amber-500 hover:text-amber-600"
              aria-label="Restart system"
              title="Restart System"
            >
              <span className="material-icons-outlined">restart_alt</span>
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleShutdown}
              className="rounded-full text-red-500 hover:text-red-600"
              aria-label="Shutdown system"
              title="Shutdown System"
            >
              <span className="material-icons-outlined">power_settings_new</span>
            </Button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className={`container mx-auto px-4 transition-all duration-300 ${
        isLogsOpen && isNowPlayingOpen ? 'pb-[576px]' :
        isLogsOpen ? 'pb-80' :
        isNowPlayingOpen ? 'pb-80' :
        'pb-20'
      }`}>
        <Outlet />
      </main>

      {/* Now Playing Bar */}
      <NowPlayingBar
        isLogsOpen={isLogsOpen}
        isVisible={isNowPlayingOpen}
        openExpanded={openNowPlayingExpanded}
        onClose={() => setIsNowPlayingOpen(false)}
      />

      {/* Floating Now Playing Button */}
      {!isNowPlayingOpen && (
        <button
          onClick={() => setIsNowPlayingOpen(true)}
          className="fixed right-4 bottom-20 z-30 w-12 h-12 rounded-full bg-primary text-primary-foreground shadow-lg flex items-center justify-center transition-all duration-200 hover:bg-primary/90 hover:shadow-xl hover:scale-110 active:scale-95"
          title="Now Playing"
        >
          <span className="material-icons">play_circle</span>
        </button>
      )}

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
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={handleCopyLogs}
                  className="rounded-full"
                  title="Copy logs"
                >
                  <span className="material-icons-outlined text-base">content_copy</span>
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={handleDownloadLogs}
                  className="rounded-full"
                  title="Download logs"
                >
                  <span className="material-icons-outlined text-base">download</span>
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => setIsLogsOpen(false)}
                  className="rounded-full"
                  title="Close logs"
                >
                  <span className="material-icons-outlined text-base">close</span>
                </Button>
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
                className={`relative flex flex-col items-center justify-center gap-1 transition-all duration-200 ${
                  isActive
                    ? 'text-primary'
                    : 'text-muted-foreground hover:text-foreground active:scale-95'
                }`}
              >
                {/* Active indicator pill */}
                {isActive && (
                  <span className="absolute -top-0.5 w-8 h-1 rounded-full bg-primary" />
                )}
                <span className={`text-xl ${isActive ? 'material-icons' : 'material-icons-outlined'}`}>
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
