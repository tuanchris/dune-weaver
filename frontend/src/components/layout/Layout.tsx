import { Outlet, Link, useLocation } from 'react-router-dom'
import { useEffect, useState, useRef } from 'react'
import { toast } from 'sonner'
import { NowPlayingBar } from '@/components/NowPlayingBar'
import { Button } from '@/components/ui/button'
import { cacheAllPreviews } from '@/lib/previewCache'

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
  const [isHoming, setIsHoming] = useState(false)
  const [homingJustCompleted, setHomingJustCompleted] = useState(false)
  const [homingCountdown, setHomingCountdown] = useState(0)
  const [keepHomingLogsOpen, setKeepHomingLogsOpen] = useState(false)
  const wasHomingRef = useRef(false)
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

  // Homing completion countdown timer
  useEffect(() => {
    if (!homingJustCompleted || keepHomingLogsOpen) return

    if (homingCountdown <= 0) {
      // Countdown finished, dismiss the overlay
      setHomingJustCompleted(false)
      setKeepHomingLogsOpen(false)
      return
    }

    const timer = setTimeout(() => {
      setHomingCountdown((prev) => prev - 1)
    }, 1000)

    return () => clearTimeout(timer)
  }, [homingJustCompleted, homingCountdown, keepHomingLogsOpen])

  // Logs drawer state
  const [isLogsOpen, setIsLogsOpen] = useState(false)
  const [logsDrawerTab, setLogsDrawerTab] = useState<'logs' | 'terminal'>('logs')
  const [logsDrawerHeight, setLogsDrawerHeight] = useState(256) // Default 256px (h-64)
  const [isResizing, setIsResizing] = useState(false)
  const isResizingRef = useRef(false)
  const startYRef = useRef(0)
  const startHeightRef = useRef(0)

  // Handle drawer resize
  const handleResizeStart = (e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault()
    isResizingRef.current = true
    setIsResizing(true)
    startYRef.current = 'touches' in e ? e.touches[0].clientY : e.clientY
    startHeightRef.current = logsDrawerHeight
    document.body.style.cursor = 'ns-resize'
    document.body.style.userSelect = 'none'
  }

  useEffect(() => {
    const handleResizeMove = (e: MouseEvent | TouchEvent) => {
      if (!isResizingRef.current) return
      const clientY = 'touches' in e ? e.touches[0].clientY : e.clientY
      const delta = startYRef.current - clientY
      const newHeight = Math.min(Math.max(startHeightRef.current + delta, 150), window.innerHeight - 150)
      setLogsDrawerHeight(newHeight)
    }

    const handleResizeEnd = () => {
      if (isResizingRef.current) {
        isResizingRef.current = false
        setIsResizing(false)
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
      }
    }

    window.addEventListener('mousemove', handleResizeMove)
    window.addEventListener('mouseup', handleResizeEnd)
    window.addEventListener('touchmove', handleResizeMove)
    window.addEventListener('touchend', handleResizeEnd)

    return () => {
      window.removeEventListener('mousemove', handleResizeMove)
      window.removeEventListener('mouseup', handleResizeEnd)
      window.removeEventListener('touchmove', handleResizeMove)
      window.removeEventListener('touchend', handleResizeEnd)
    }
  }, [])

  // Serial terminal state
  const [serialPorts, setSerialPorts] = useState<string[]>([])
  const [selectedSerialPort, setSelectedSerialPort] = useState('')
  const [serialConnected, setSerialConnected] = useState(false)
  const [serialCommand, setSerialCommand] = useState('')
  const [serialHistory, setSerialHistory] = useState<Array<{ type: 'cmd' | 'resp' | 'error'; text: string; time: string }>>([])
  const [serialLoading, setSerialLoading] = useState(false)
  const serialOutputRef = useRef<HTMLDivElement>(null)

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
            // Update homing status and detect completion
            if (data.data.is_homing !== undefined) {
              const newIsHoming = data.data.is_homing
              // Detect transition from homing to not homing
              if (wasHomingRef.current && !newIsHoming) {
                // Homing just completed - show completion state with countdown
                setHomingJustCompleted(true)
                setHomingCountdown(5)
              }
              wasHomingRef.current = newIsHoming
              setIsHoming(newIsHoming)
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

  // Serial terminal functions
  const fetchSerialPorts = async () => {
    try {
      const response = await fetch('/list_serial_ports')
      const data = await response.json()
      // API returns array directly, not wrapped in object
      setSerialPorts(Array.isArray(data) ? data : [])
    } catch {
      toast.error('Failed to fetch serial ports')
    }
  }

  const handleSerialConnect = async () => {
    if (!selectedSerialPort) {
      toast.error('Please select a port')
      return
    }

    setSerialLoading(true)
    try {
      const response = await fetch('/api/debug-serial/open', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ port: selectedSerialPort }),
      })
      const data = await response.json()
      if (data.success) {
        setSerialConnected(true)
        addSerialHistory('resp', `Connected to ${selectedSerialPort}`)
        toast.success(`Connected to ${selectedSerialPort}`)
      } else {
        throw new Error(data.detail || 'Connection failed')
      }
    } catch (error) {
      addSerialHistory('error', `Failed to connect: ${error}`)
      toast.error('Failed to connect to serial port')
    } finally {
      setSerialLoading(false)
    }
  }

  const handleSerialDisconnect = async () => {
    setSerialLoading(true)
    try {
      await fetch('/api/debug-serial/close', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ port: selectedSerialPort }),
      })
      setSerialConnected(false)
      addSerialHistory('resp', 'Disconnected')
      toast.success('Disconnected from serial port')
    } catch {
      toast.error('Failed to disconnect')
    } finally {
      setSerialLoading(false)
    }
  }

  const addSerialHistory = (type: 'cmd' | 'resp' | 'error', text: string) => {
    const time = new Date().toLocaleTimeString()
    setSerialHistory((prev) => [...prev.slice(-200), { type, text, time }])
    setTimeout(() => {
      if (serialOutputRef.current) {
        serialOutputRef.current.scrollTop = serialOutputRef.current.scrollHeight
      }
    }, 10)
  }

  const serialInputRef = useRef<HTMLInputElement>(null)

  const handleSerialSend = async () => {
    if (!serialCommand.trim() || !serialConnected || serialLoading) return

    const cmd = serialCommand.trim()
    setSerialCommand('')
    setSerialLoading(true)
    addSerialHistory('cmd', cmd)

    try {
      const response = await fetch('/api/debug-serial/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ port: selectedSerialPort, command: cmd }),
      })
      const data = await response.json()
      if (data.success) {
        if (data.responses && data.responses.length > 0) {
          data.responses.forEach((line: string) => addSerialHistory('resp', line))
        } else {
          addSerialHistory('resp', '(no response)')
        }
      } else {
        addSerialHistory('error', data.detail || 'Command failed')
      }
    } catch (error) {
      addSerialHistory('error', `Error: ${error}`)
    } finally {
      setSerialLoading(false)
      // Keep focus on input after sending
      serialInputRef.current?.focus()
    }
  }

  const handleSerialKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      e.stopPropagation()
      // Keep focus on the input
      const input = e.currentTarget
      handleSerialSend()
      // Ensure focus stays on input
      requestAnimationFrame(() => input.focus())
    }
  }

  // Fetch serial ports when terminal tab is selected
  useEffect(() => {
    if (isLogsOpen && logsDrawerTab === 'terminal') {
      fetchSerialPorts()
    }
  }, [isLogsOpen, logsDrawerTab])

  const handleRestart = async () => {
    if (!confirm('Are you sure you want to restart Docker containers?')) return

    try {
      const response = await fetch('/api/system/restart', { method: 'POST' })
      if (response.ok) {
        toast.success('Docker containers are restarting...')
      } else {
        throw new Error('Restart failed')
      }
    } catch {
      toast.error('Failed to restart Docker containers')
    }
  }

  const handleShutdown = async () => {
    if (!confirm('Are you sure you want to shutdown the system?')) return

    try {
      const response = await fetch('/api/system/shutdown', { method: 'POST' })
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

  // Blocking overlay logs WebSocket ref
  const blockingLogsWsRef = useRef<WebSocket | null>(null)

  // Add connection/homing logs when overlay is shown
  useEffect(() => {
    const showOverlay = !isBackendConnected || isHoming || homingJustCompleted

    if (!showOverlay) {
      setConnectionLogs([])
      // Close WebSocket if open
      if (blockingLogsWsRef.current) {
        blockingLogsWsRef.current.close()
        blockingLogsWsRef.current = null
      }
      return
    }

    // Don't clear logs or reconnect WebSocket during completion state
    if (homingJustCompleted && !isHoming) {
      return
    }

    // Add log entry helper
    const addLog = (level: string, message: string, timestamp?: string) => {
      setConnectionLogs((prev) => {
        const newLog = {
          timestamp: timestamp || new Date().toISOString(),
          level,
          message,
        }
        const newLogs = [...prev, newLog].slice(-100) // Keep last 100 entries
        return newLogs
      })
      // Auto-scroll to bottom
      setTimeout(() => {
        if (blockingLogsRef.current) {
          blockingLogsRef.current.scrollTop = blockingLogsRef.current.scrollHeight
        }
      }, 10)
    }

    // If homing, connect to logs WebSocket to stream real logs
    if (isHoming && isBackendConnected) {
      addLog('INFO', 'Homing started...')

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws/logs`)

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          if (message.type === 'heartbeat') return

          const log = message.type === 'log_entry' ? message.data : message
          if (!log || !log.message || log.message.trim() === '') return

          // Filter for homing-related logs
          const msg = log.message.toLowerCase()
          const isHomingLog =
            msg.includes('homing') ||
            msg.includes('home') ||
            msg.includes('$h') ||
            msg.includes('idle') ||
            msg.includes('unlock') ||
            msg.includes('alarm') ||
            msg.includes('grbl') ||
            msg.includes('connect') ||
            msg.includes('serial') ||
            msg.includes('device') ||
            msg.includes('position') ||
            msg.includes('zeroing') ||
            msg.includes('movement') ||
            log.logger?.includes('connection')

          if (isHomingLog) {
            addLog(log.level, log.message, log.timestamp)
          }
        } catch {
          // Ignore parse errors
        }
      }

      blockingLogsWsRef.current = ws

      return () => {
        ws.close()
        blockingLogsWsRef.current = null
      }
    }

    // If backend disconnected, show connection retry logs
    if (!isBackendConnected) {
      addLog('INFO', `Attempting to connect to backend at ${window.location.host}...`)

      const interval = setInterval(() => {
        addLog('INFO', `Retrying connection to WebSocket /ws/status...`)

        fetch('/api/settings', { method: 'GET' })
          .then(() => {
            addLog('INFO', 'HTTP endpoint responding, waiting for WebSocket...')
          })
          .catch(() => {
            // Still down
          })
      }, 3000)

      return () => clearInterval(interval)
    }
  }, [isBackendConnected, isHoming, homingJustCompleted])

  // Cache progress WebSocket connection - always connected to monitor cache generation
  useEffect(() => {
    if (!isBackendConnected) return

    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null

    const connectCacheWebSocket = () => {
      if (cacheWsRef.current) return

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws/cache-progress`)

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          if (message.type === 'cache_progress') {
            const data = message.data
            if (data.is_running) {
              // Cache generation is running - show splash screen
              setCacheProgress(data)
            } else if (data.stage === 'complete') {
              // Cache generation just completed
              if (cacheProgress?.is_running) {
                // Was running before, now complete - show cache all prompt
                const promptShown = localStorage.getItem('cacheAllPromptShown')
                if (!promptShown) {
                  setTimeout(() => {
                    setCacheAllProgress(null) // Reset to clean state
                    setShowCacheAllPrompt(true)
                  }, 500)
                }
              }
              setCacheProgress(null)
            } else {
              // Not running and not complete (idle state)
              setCacheProgress(null)
            }
          }
        } catch {
          // Ignore parse errors
        }
      }

      ws.onclose = () => {
        cacheWsRef.current = null
        // Reconnect after 3 seconds
        if (isBackendConnected) {
          reconnectTimeout = setTimeout(connectCacheWebSocket, 3000)
        }
      }

      ws.onerror = () => {
        // Will trigger onclose
      }

      cacheWsRef.current = ws
    }

    connectCacheWebSocket()

    return () => {
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout)
      }
      if (cacheWsRef.current) {
        cacheWsRef.current.close()
        cacheWsRef.current = null
      }
    }
  }, [isBackendConnected]) // Only reconnect based on backend connection, not cache state

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

  // Cache all previews in browser using IndexedDB
  const handleCacheAllPreviews = async () => {
    setCacheAllProgress({ inProgress: true, completed: 0, total: 0, done: false })

    const result = await cacheAllPreviews((progress) => {
      setCacheAllProgress({ inProgress: !progress.done, ...progress })
    })

    if (result.success) {
      if (result.cached === 0) {
        toast.success('All patterns are already cached!')
      } else {
        toast.success(`Cached ${result.cached} pattern previews`)
      }
    } else {
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

                {/* Initial state - show buttons */}
                {!cacheAllProgress && (
                  <div className="flex gap-3 justify-center">
                    <Button variant="ghost" onClick={handleSkipCacheAll}>
                      Skip for now
                    </Button>
                    <Button variant="outline" onClick={handleCacheAllPreviews} className="gap-2">
                      <span className="material-icons-outlined text-lg">cached</span>
                      Cache All
                    </Button>
                  </div>
                )}

                {/* Progress section */}
                {cacheAllProgress && !cacheAllProgress.done && (
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
                      All {cacheAllProgress.total} previews cached successfully!
                    </p>
                    <Button onClick={handleCloseCacheAllDone} className="w-full">
                      Done
                    </Button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Backend Connection / Homing Blocking Overlay */}
      {(!isBackendConnected || isHoming || homingJustCompleted) && (
        <div className="fixed inset-0 z-50 bg-background/95 backdrop-blur-sm flex flex-col items-center justify-center p-4">
          <div className="w-full max-w-2xl space-y-6">
            {/* Status Header */}
            <div className="text-center space-y-4">
              <div className={`inline-flex items-center justify-center w-16 h-16 rounded-full mb-2 ${
                homingJustCompleted
                  ? 'bg-green-500/10'
                  : isHoming
                    ? 'bg-primary/10'
                    : 'bg-amber-500/10'
              }`}>
                <span className={`material-icons-outlined text-4xl ${
                  homingJustCompleted
                    ? 'text-green-500'
                    : isHoming
                      ? 'text-primary animate-spin'
                      : 'text-amber-500 animate-pulse'
                }`}>
                  {homingJustCompleted ? 'check_circle' : 'sync'}
                </span>
              </div>
              <h2 className="text-2xl font-bold">
                {homingJustCompleted
                  ? 'Homing Complete'
                  : isHoming
                    ? 'Homing in Progress'
                    : 'Connecting to Backend'
                }
              </h2>
              <p className="text-muted-foreground">
                {homingJustCompleted
                  ? 'Table is ready to use'
                  : isHoming
                    ? 'Moving to home position... This may take up to 90 seconds.'
                    : connectionAttempts === 0
                      ? 'Establishing connection...'
                      : `Reconnecting... (attempt ${connectionAttempts})`
                }
              </p>
              <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
                <span className={`w-2 h-2 rounded-full ${
                  homingJustCompleted
                    ? 'bg-green-500'
                    : isHoming
                      ? 'bg-primary animate-pulse'
                      : 'bg-amber-500 animate-pulse'
                }`} />
                <span>
                  {homingJustCompleted
                    ? keepHomingLogsOpen
                      ? 'Viewing logs'
                      : `Closing in ${homingCountdown}s...`
                    : isHoming
                      ? 'Do not interrupt the homing process'
                      : `Waiting for server at ${window.location.host}`
                  }
                </span>
              </div>
            </div>

            {/* Logs Panel */}
            <div className="bg-muted/50 rounded-lg border overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2 border-b bg-muted">
                <div className="flex items-center gap-2">
                  <span className="material-icons-outlined text-base">terminal</span>
                  <span className="text-sm font-medium">
                    {isHoming || homingJustCompleted ? 'Homing Log' : 'Connection Log'}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      const logText = connectionLogs
                        .map((log) => `[${new Date(log.timestamp).toLocaleTimeString()}] [${log.level}] ${log.message}`)
                        .join('\n')
                      navigator.clipboard.writeText(logText).then(() => {
                        toast.success('Logs copied to clipboard')
                      }).catch(() => {
                        toast.error('Failed to copy logs')
                      })
                    }}
                    className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
                    title="Copy logs to clipboard"
                  >
                    <span className="material-icons text-sm">content_copy</span>
                    Copy
                  </button>
                  <span className="text-xs text-muted-foreground">
                    {connectionLogs.length} entries
                  </span>
                </div>
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

            {/* Action buttons for homing completion */}
            {homingJustCompleted && (
              <div className="flex justify-center gap-3">
                {!keepHomingLogsOpen ? (
                  <>
                    <Button
                      variant="outline"
                      onClick={() => setKeepHomingLogsOpen(true)}
                      className="gap-2"
                    >
                      <span className="material-icons text-base">visibility</span>
                      Keep Open
                    </Button>
                    <Button
                      onClick={() => {
                        setHomingJustCompleted(false)
                        setKeepHomingLogsOpen(false)
                      }}
                      className="gap-2"
                    >
                      <span className="material-icons text-base">close</span>
                      Dismiss
                    </Button>
                  </>
                ) : (
                  <Button
                    onClick={() => {
                      setHomingJustCompleted(false)
                      setKeepHomingLogsOpen(false)
                    }}
                    className="gap-2"
                  >
                    <span className="material-icons text-base">close</span>
                    Close Logs
                  </Button>
                )}
              </div>
            )}

            {/* Hint */}
            {!homingJustCompleted && (
              <p className="text-center text-xs text-muted-foreground">
                {isHoming
                  ? 'The table is calibrating its position'
                  : 'Make sure the backend server is running on port 8080'
                }
              </p>
            )}
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
              className={`w-2 h-2 rounded-full ${
                !isBackendConnected
                  ? 'bg-gray-400'
                  : isConnected
                    ? 'bg-green-500 animate-pulse'
                    : 'bg-red-500'
              }`}
              title={
                !isBackendConnected
                  ? 'Backend not connected'
                  : isConnected
                    ? 'Table connected'
                    : 'Table disconnected'
              }
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
              aria-label="Restart Docker"
              title="Restart Docker"
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
      <main
        className={`container mx-auto px-4 transition-all duration-300 ${
          !isLogsOpen && !isNowPlayingOpen ? 'pb-20' :
          !isLogsOpen && isNowPlayingOpen ? 'pb-80' : ''
        }`}
        style={{
          paddingBottom: isLogsOpen
            ? isNowPlayingOpen
              ? logsDrawerHeight + 256 + 64 // drawer + now playing + nav
              : logsDrawerHeight + 64 // drawer + nav
            : undefined
        }}
      >
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
        className={`fixed left-0 right-0 z-30 bg-background border-t border-border bottom-16 ${
          isResizing ? '' : 'transition-[height] duration-300'
        }`}
        style={{ height: isLogsOpen ? logsDrawerHeight : 0 }}
      >
        {isLogsOpen && (
          <>
            {/* Resize Handle */}
            <div
              className="absolute top-0 left-0 right-0 h-2 cursor-ns-resize flex items-center justify-center group hover:bg-primary/10 -translate-y-1/2 z-10"
              onMouseDown={handleResizeStart}
              onTouchStart={handleResizeStart}
            >
              <div className="w-12 h-1 rounded-full bg-border group-hover:bg-primary transition-colors" />
            </div>

            {/* Tab Header */}
            <div className="flex items-center justify-between px-4 py-2 border-b bg-muted/50">
              <div className="flex items-center gap-3">
                {/* Tab Buttons */}
                <div className="flex rounded-md border bg-background p-0.5">
                  <button
                    onClick={() => setLogsDrawerTab('logs')}
                    className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                      logsDrawerTab === 'logs'
                        ? 'bg-primary text-primary-foreground'
                        : 'hover:bg-muted'
                    }`}
                  >
                    Logs
                  </button>
                  <button
                    onClick={() => setLogsDrawerTab('terminal')}
                    className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                      logsDrawerTab === 'terminal'
                        ? 'bg-primary text-primary-foreground'
                        : 'hover:bg-muted'
                    }`}
                  >
                    Serial Terminal
                  </button>
                </div>

                {/* Logs tab controls */}
                {logsDrawerTab === 'logs' && (
                  <>
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
                  </>
                )}

                {/* Serial terminal controls */}
                {logsDrawerTab === 'terminal' && (
                  <div className="flex items-center gap-2">
                    <select
                      value={selectedSerialPort}
                      onChange={(e) => setSelectedSerialPort(e.target.value)}
                      disabled={serialConnected || serialLoading}
                      className="text-xs bg-background border rounded px-2 py-1 min-w-[140px]"
                    >
                      <option value="">Select port...</option>
                      {serialPorts.map((port) => (
                        <option key={port} value={port}>{port}</option>
                      ))}
                    </select>
                    <button
                      onClick={fetchSerialPorts}
                      disabled={serialConnected || serialLoading}
                      className="text-xs text-muted-foreground hover:text-foreground"
                      title="Refresh ports"
                    >
                      <span className="material-icons text-sm">refresh</span>
                    </button>
                    {!serialConnected ? (
                      <Button
                        size="sm"
                        onClick={handleSerialConnect}
                        disabled={!selectedSerialPort || serialLoading}
                        className="h-6 text-xs px-2"
                      >
                        Connect
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={handleSerialDisconnect}
                        disabled={serialLoading}
                        className="h-6 text-xs px-2"
                      >
                        Disconnect
                      </Button>
                    )}
                    {serialConnected && (
                      <span className="flex items-center gap-1 text-xs text-green-600">
                        <span className="w-2 h-2 rounded-full bg-green-500" />
                        Connected
                      </span>
                    )}
                  </div>
                )}
              </div>

              <div className="flex items-center gap-1">
                {logsDrawerTab === 'logs' && (
                  <>
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
                  </>
                )}
                {logsDrawerTab === 'terminal' && serialHistory.length > 0 && (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => setSerialHistory([])}
                    className="rounded-full"
                    title="Clear history"
                  >
                    <span className="material-icons-outlined text-base">delete_sweep</span>
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => setIsLogsOpen(false)}
                  className="rounded-full"
                  title="Close"
                >
                  <span className="material-icons-outlined text-base">close</span>
                </Button>
              </div>
            </div>

            {/* Logs Content */}
            {logsDrawerTab === 'logs' && (
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
            )}

            {/* Serial Terminal Content */}
            {logsDrawerTab === 'terminal' && (
              <div className="h-[calc(100%-40px)] flex flex-col">
                {/* Output area */}
                <div
                  ref={serialOutputRef}
                  className="flex-1 overflow-auto overscroll-contain p-3 font-mono text-xs space-y-0.5 bg-black/5 dark:bg-white/5"
                >
                  {serialHistory.length > 0 ? (
                    serialHistory.map((entry, i) => (
                      <div key={i} className="py-0.5 flex gap-2">
                        <span className="text-muted-foreground shrink-0">{entry.time}</span>
                        {entry.type === 'cmd' ? (
                          <>
                            <span className="text-blue-500 shrink-0">&gt;</span>
                            <span className="text-blue-600 dark:text-blue-400">{entry.text}</span>
                          </>
                        ) : entry.type === 'error' ? (
                          <>
                            <span className="text-red-500 shrink-0">!</span>
                            <span className="text-red-500">{entry.text}</span>
                          </>
                        ) : (
                          <>
                            <span className="text-green-500 shrink-0">&lt;</span>
                            <span className="text-foreground">{entry.text}</span>
                          </>
                        )}
                      </div>
                    ))
                  ) : (
                    <p className="text-muted-foreground text-center py-4">
                      {serialConnected
                        ? 'Type a command and press Enter to send'
                        : 'Select a port and click Connect to start'}
                    </p>
                  )}
                </div>
                {/* Command input */}
                <div className="flex items-center gap-3 px-3 py-3 pr-5 border-t bg-muted/30">
                  <span className="text-muted-foreground font-mono text-base">&gt;</span>
                  <input
                    ref={serialInputRef}
                    type="text"
                    value={serialCommand}
                    onChange={(e) => setSerialCommand(e.target.value)}
                    onKeyDown={handleSerialKeyDown}
                    disabled={!serialConnected}
                    readOnly={serialLoading}
                    placeholder={serialConnected ? 'Enter command (e.g., $, $$, ?, $H)' : 'Connect to send commands'}
                    className="flex-1 bg-transparent border-none outline-none font-mono text-base placeholder:text-muted-foreground h-8"
                    autoComplete="off"
                  />
                  <Button
                    size="sm"
                    onClick={handleSerialSend}
                    disabled={!serialConnected || !serialCommand.trim() || serialLoading}
                    className="h-8 px-4 shrink-0"
                  >
                    {serialLoading ? (
                      <span className="material-icons animate-spin text-sm">sync</span>
                    ) : (
                      'Send'
                    )}
                  </Button>
                </div>
              </div>
            )}
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
