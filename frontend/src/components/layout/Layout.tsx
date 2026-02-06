import { Outlet, Link, useLocation } from 'react-router-dom'
import { useEffect, useState, useRef, useCallback, useMemo } from 'react'
import { toast } from 'sonner'
import { NowPlayingBar } from '@/components/NowPlayingBar'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Separator } from '@/components/ui/separator'
import { cacheAllPreviews } from '@/lib/previewCache'
import { TableSelector } from '@/components/TableSelector'
import { useTable } from '@/contexts/TableContext'
import { apiClient } from '@/lib/apiClient'
import ShinyText from '@/components/ShinyText'

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

  // Scroll to top on route change
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [location.pathname])

  // Multi-table context - must be called before any hooks that depend on activeTable
  const { activeTable, tables } = useTable()

  // Use table name as app name when multiple tables exist
  const hasMultipleTables = tables.length > 1

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

  // Display name: when multiple tables exist, use the active table's name; otherwise use app settings
  // Get the table from the tables array (most up-to-date source) to ensure we have current data
  const activeTableData = tables.find(t => t.id === activeTable?.id)
  const tableName = activeTableData?.name || activeTable?.name
  const displayName = hasMultipleTables && tableName ? tableName : appName

  // Connection status
  const [isConnected, setIsConnected] = useState(false)
  const [isBackendConnected, setIsBackendConnected] = useState(false)
  const [isHoming, setIsHoming] = useState(false)
  const [homingDismissed, setHomingDismissed] = useState(false)
  const [homingJustCompleted, setHomingJustCompleted] = useState(false)
  const [homingCountdown, setHomingCountdown] = useState(0)
  const [keepHomingLogsOpen, setKeepHomingLogsOpen] = useState(false)
  const wasHomingRef = useRef(false)
  const [connectionAttempts, setConnectionAttempts] = useState(0)
  const wsRef = useRef<WebSocket | null>(null)

  // Sensor homing failure state
  const [sensorHomingFailed, setSensorHomingFailed] = useState(false)
  const [isRecoveringHoming, setIsRecoveringHoming] = useState(false)

  // Update availability
  const [updateAvailable, setUpdateAvailable] = useState(false)

  // Fetch app settings
  const fetchAppSettings = () => {
    apiClient.get<{ app?: { name?: string; custom_logo?: string } }>('/api/settings')
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
    // Refetch when active table changes
  }, [activeTable?.id])

  // Check for software updates on mount
  useEffect(() => {
    apiClient.get<{ update_available?: boolean }>('/api/version')
      .then((data) => {
        if (data.update_available) {
          setUpdateAvailable(true)
        }
      })
      .catch(() => {})
  }, [activeTable?.id])

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

  // Mobile menu state
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)

  // Logs drawer state
  const [isLogsOpen, setIsLogsOpen] = useState(false)
  const [logsDrawerHeight, setLogsDrawerHeight] = useState(256) // Default 256px (h-64)
  const [isResizing, setIsResizing] = useState(false)
  const isResizingRef = useRef(false)
  const startYRef = useRef(0)
  const startHeightRef = useRef(0)

  const [logSearchQuery, setLogSearchQuery] = useState('')

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

  // Now Playing bar state
  const [isNowPlayingOpen, setIsNowPlayingOpen] = useState(false)
  const [openNowPlayingExpanded, setOpenNowPlayingExpanded] = useState(false)
  const [currentPlayingFile, setCurrentPlayingFile] = useState<string | null>(null) // Track current file for header button
  const wasPlayingRef = useRef<boolean | null>(null) // Track previous playing state (null = first message)

  // Draggable Now Playing button state
  type SnapPosition = 'left' | 'center' | 'right'
  const [nowPlayingButtonPos, setNowPlayingButtonPos] = useState<SnapPosition>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('nowPlayingButtonPos')
      if (saved === 'left' || saved === 'center' || saved === 'right') return saved
    }
    return 'center'
  })
  const [isDraggingButton, setIsDraggingButton] = useState(false)
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 })
  const buttonRef = useRef<HTMLButtonElement>(null)
  const dragStartRef = useRef<{ x: number; y: number; buttonX: number } | null>(null)
  const wasDraggingRef = useRef(false) // Track if a meaningful drag occurred

  // Derive isCurrentlyPlaying from currentPlayingFile
  const isCurrentlyPlaying = Boolean(currentPlayingFile)

  // Listen for playback-started event (dispatched when user starts a pattern)
  useEffect(() => {
    const handlePlaybackStarted = () => {
      setIsNowPlayingOpen(true)
      setOpenNowPlayingExpanded(true)
      setIsLogsOpen(false)
      // Reset expanded flag after animation
      setTimeout(() => setOpenNowPlayingExpanded(false), 500)
    }
    window.addEventListener('playback-started', handlePlaybackStarted)
    return () => window.removeEventListener('playback-started', handlePlaybackStarted)
  }, [])
  const [logs, setLogs] = useState<Array<{ timestamp: string; level: string; logger: string; message: string }>>([])
  const [logLevelFilter, setLogLevelFilter] = useState<string>('ALL')
  const [logsTotal, setLogsTotal] = useState(0)
  const [logsHasMore, setLogsHasMore] = useState(false)
  const [isLoadingMoreLogs, setIsLoadingMoreLogs] = useState(false)
  const logsWsRef = useRef<WebSocket | null>(null)
  const logsContainerRef = useRef<HTMLDivElement>(null)
  const logsLoadedCountRef = useRef(0) // Track how many logs we've loaded (for offset)

  // Check device connection status via WebSocket
  // This effect runs once on mount and manages its own reconnection logic
  useEffect(() => {
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null
    let isMounted = true

    const connectWebSocket = () => {
      if (!isMounted) return

      // Only close existing connection if it's open (not still connecting)
      // This prevents "WebSocket closed before connection established" errors
      if (wsRef.current) {
        if (wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.close()
          wsRef.current = null
        } else if (wsRef.current.readyState === WebSocket.CONNECTING) {
          // Already connecting, don't interrupt
          return
        }
      }

      const ws = new WebSocket(apiClient.getWebSocketUrl('/ws/status'))
      // Assign to ref IMMEDIATELY so concurrent calls see it's connecting
      wsRef.current = ws

      ws.onopen = () => {
        if (!isMounted) {
          // Component unmounted while connecting - close the WebSocket now
          ws.close()
          return
        }
        setIsBackendConnected(true)
        setConnectionAttempts(0)
        // Dispatch event so pages can refetch data
        window.dispatchEvent(new CustomEvent('backend-connected'))
      }

      ws.onmessage = (event) => {
        if (!isMounted) return
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
              // Detect transition from not homing to homing - reset dismissal
              if (!wasHomingRef.current && newIsHoming) {
                setHomingDismissed(false)
              }
              // Detect transition from homing to not homing
              if (wasHomingRef.current && !newIsHoming) {
                // Homing just completed - show completion state with countdown
                // But not if sensor homing failed (that shows a different dialog)
                if (!data.data.sensor_homing_failed) {
                  setHomingJustCompleted(true)
                  setHomingCountdown(5)
                  setHomingDismissed(false)
                }
              }
              wasHomingRef.current = newIsHoming
              setIsHoming(newIsHoming)
            }
            // Update sensor homing failure status
            if (data.data.sensor_homing_failed !== undefined) {
              setSensorHomingFailed(data.data.sensor_homing_failed)
            }
            // Auto-open/close Now Playing bar based on playback state
            // Track current file - this is the most reliable indicator of playback
            const currentFile = data.data.current_file || null
            setCurrentPlayingFile(currentFile)

            // Include pause_time_remaining to keep bar visible during countdown between patterns
            const isPlaying = Boolean(currentFile) || Boolean(data.data.is_running) || Boolean(data.data.is_paused) || (data.data.pause_time_remaining ?? 0) > 0
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
        if (!isMounted) return
        wsRef.current = null
        setIsBackendConnected(false)
        setConnectionAttempts((prev) => prev + 1)
        // Reconnect after 3 seconds (don't change device status on WS disconnect)
        reconnectTimeout = setTimeout(connectWebSocket, 3000)
      }

      ws.onerror = () => {
        if (!isMounted) return
        setIsBackendConnected(false)
      }
    }

    // Reset playing state on mount
    wasPlayingRef.current = null

    // Connect on mount
    connectWebSocket()

    // Subscribe to base URL changes (when user switches tables)
    // This triggers reconnection to the new backend
    const unsubscribe = apiClient.onBaseUrlChange(() => {
      if (isMounted) {
        wasPlayingRef.current = null // Reset playing state for new table
        setCurrentPlayingFile(null) // Reset playback state for new table
        setIsConnected(false) // Reset connection status until new table reports
        setIsBackendConnected(false) // Show connecting state
        setSensorHomingFailed(false) // Reset sensor homing failure state for new table
        connectWebSocket()
      }
    })

    return () => {
      isMounted = false
      unsubscribe()
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout)
      }
      if (wsRef.current) {
        // Only close if already OPEN - CONNECTING WebSockets will close in onopen
        if (wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.close()
        }
        wsRef.current = null
      }
    }
  }, []) // Empty deps - runs once on mount, reconnects via apiClient listener

  // Connect to logs WebSocket when drawer opens
  useEffect(() => {
    if (!isLogsOpen) {
      // Close WebSocket when drawer closes - only if OPEN (CONNECTING will close in onopen)
      if (logsWsRef.current && logsWsRef.current.readyState === WebSocket.OPEN) {
        logsWsRef.current.close()
      }
      logsWsRef.current = null
      return
    }

    let shouldConnect = true

    // Fetch initial logs (most recent)
    const fetchInitialLogs = async () => {
      try {
        type LogEntry = { timestamp: string; level: string; logger: string; message: string }
        type LogsResponse = { logs: LogEntry[]; total: number; has_more: boolean }
        const data = await apiClient.get<LogsResponse>('/api/logs?limit=200')
        // Filter out empty/invalid log entries
        const validLogs = (data.logs || []).filter(
          (log) => log && log.message && log.message.trim() !== ''
        )
        // API returns newest first, reverse to show oldest first (newest at bottom)
        setLogs(validLogs.reverse())
        setLogsTotal(data.total || 0)
        setLogsHasMore(data.has_more || false)
        logsLoadedCountRef.current = validLogs.length
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
      // Don't interrupt an existing connection that's still connecting
      if (logsWsRef.current) {
        if (logsWsRef.current.readyState === WebSocket.CONNECTING) {
          return // Already connecting, wait for it
        }
        if (logsWsRef.current.readyState === WebSocket.OPEN) {
          logsWsRef.current.close()
        }
        logsWsRef.current = null
      }

      const ws = new WebSocket(apiClient.getWebSocketUrl('/ws/logs'))
      // Assign to ref IMMEDIATELY so concurrent calls see it's connecting
      logsWsRef.current = ws

      ws.onopen = () => {
        if (!shouldConnect) {
          // Effect cleanup ran while connecting - close now
          ws.close()
          return
        }
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
          // Append new log - no limit, lazy loading handles old logs
          setLogs((prev) => [...prev, log])
          // Auto-scroll to bottom if user is near the bottom
          setTimeout(() => {
            if (logsContainerRef.current) {
              const { scrollTop, scrollHeight, clientHeight } = logsContainerRef.current
              // Only auto-scroll if user is within 100px of the bottom
              if (scrollHeight - scrollTop - clientHeight < 100) {
                logsContainerRef.current.scrollTop = scrollHeight
              }
            }
          }, 10)
        } catch {
          // Ignore parse errors
        }
      }

      ws.onclose = () => {
        if (!shouldConnect) return
        console.log('Logs WebSocket closed, reconnecting...')
        // Reconnect after 3 seconds if drawer is still open
        reconnectTimeout = setTimeout(() => {
          if (shouldConnect && logsWsRef.current === ws) {
            connectLogsWebSocket()
          }
        }, 3000)
      }

      ws.onerror = (error) => {
        console.error('Logs WebSocket error:', error)
      }
    }

    connectLogsWebSocket()

    return () => {
      shouldConnect = false
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout)
      }
      if (logsWsRef.current) {
        // Only close if already OPEN - CONNECTING WebSockets will close in onopen
        if (logsWsRef.current.readyState === WebSocket.OPEN) {
          logsWsRef.current.close()
        }
        logsWsRef.current = null
      }
    }
    // Also reconnect when active table changes
  }, [isLogsOpen, activeTable?.id])

  // Load older logs when user scrolls to top (lazy loading)
  const loadOlderLogs = useCallback(async () => {
    if (isLoadingMoreLogs || !logsHasMore) return

    setIsLoadingMoreLogs(true)
    try {
      type LogEntry = { timestamp: string; level: string; logger: string; message: string }
      type LogsResponse = { logs: LogEntry[]; total: number; has_more: boolean }
      const offset = logsLoadedCountRef.current
      const data = await apiClient.get<LogsResponse>(`/api/logs?limit=100&offset=${offset}`)

      const validLogs = (data.logs || []).filter(
        (log) => log && log.message && log.message.trim() !== ''
      )

      if (validLogs.length > 0) {
        // Prepend older logs (they come newest-first, so reverse them)
        setLogs((prev) => [...validLogs.reverse(), ...prev])
        logsLoadedCountRef.current += validLogs.length
        setLogsHasMore(data.has_more || false)
        setLogsTotal(data.total || 0)

        // Maintain scroll position after prepending
        setTimeout(() => {
          if (logsContainerRef.current) {
            // Calculate approximate height of new content (rough estimate: 24px per log line)
            const newContentHeight = validLogs.length * 24
            logsContainerRef.current.scrollTop = newContentHeight
          }
        }, 10)
      } else {
        setLogsHasMore(false)
      }
    } catch {
      // Ignore errors
    } finally {
      setIsLoadingMoreLogs(false)
    }
  }, [isLoadingMoreLogs, logsHasMore])

  // Scroll event handler for lazy loading
  useEffect(() => {
    const container = logsContainerRef.current
    if (!container || !isLogsOpen) return

    const handleScroll = () => {
      // Load more when scrolled to top (within 50px)
      if (container.scrollTop < 50 && logsHasMore && !isLoadingMoreLogs) {
        loadOlderLogs()
      }
    }

    container.addEventListener('scroll', handleScroll)
    return () => container.removeEventListener('scroll', handleScroll)
  }, [isLogsOpen, logsHasMore, isLoadingMoreLogs, loadOlderLogs])

  const handleToggleLogs = () => {
    setIsLogsOpen((prev) => !prev)
  }

  // Filter logs by level and search query
  const filteredLogs = useMemo(() => {
    let result = logLevelFilter === 'ALL'
      ? logs
      : logs.filter((log) => log.level === logLevelFilter)
    if (logSearchQuery) {
      const q = logSearchQuery.toLowerCase()
      result = result.filter((log) =>
        log.message?.toLowerCase().includes(q) ||
        log.logger?.toLowerCase().includes(q)
      )
    }
    return result
  }, [logs, logLevelFilter, logSearchQuery])

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

  // Copy logs to clipboard (with fallback for non-HTTPS)
  const handleCopyLogs = () => {
    const text = filteredLogs
      .map((log) => `${formatTimestamp(log.timestamp)} [${log.level}] ${log.message}`)
      .join('\n')
    copyToClipboard(text)
  }

  // Helper to copy text with fallback for non-secure contexts
  const copyToClipboard = (text: string) => {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(() => {
        toast.success('Logs copied to clipboard')
      }).catch(() => {
        toast.error('Failed to copy logs')
      })
    } else {
      // Fallback for non-secure contexts (http://)
      const textArea = document.createElement('textarea')
      textArea.value = text
      textArea.style.position = 'fixed'
      textArea.style.left = '-9999px'
      document.body.appendChild(textArea)
      textArea.select()
      try {
        document.execCommand('copy')
        toast.success('Logs copied to clipboard')
      } catch {
        toast.error('Failed to copy logs')
      }
      document.body.removeChild(textArea)
    }
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
    if (!confirm('Are you sure you want to restart Docker containers?')) return

    try {
      await apiClient.post('/api/system/restart')
      toast.success('Docker containers are restarting...')
    } catch {
      toast.error('Failed to restart Docker containers')
    }
  }

  const handleShutdown = async () => {
    if (!confirm('Are you sure you want to shutdown the system?')) return

    try {
      await apiClient.post('/api/system/shutdown')
      toast.success('System is shutting down...')
    } catch {
      toast.error('Failed to shutdown system')
    }
  }

  // Handle sensor homing recovery
  const handleSensorHomingRecovery = async (switchToCrashHoming: boolean) => {
    setIsRecoveringHoming(true)
    try {
      const response = await apiClient.post<{
        success: boolean
        sensor_homing_failed?: boolean
        message?: string
      }>('/recover_sensor_homing', {
        switch_to_crash_homing: switchToCrashHoming
      })

      if (response.success) {
        toast.success(response.message || 'Homing completed successfully')
        setSensorHomingFailed(false)
      } else if (response.sensor_homing_failed) {
        // Sensor homing failed again
        toast.error(response.message || 'Sensor homing failed again')
      } else {
        toast.error(response.message || 'Recovery failed')
      }
    } catch {
      toast.error('Failed to recover from sensor homing failure')
    } finally {
      setIsRecoveringHoming(false)
    }
  }

  // Update document title based on current page
  useEffect(() => {
    const currentNav = navItems.find((item) => item.path === location.pathname)
    if (currentNav) {
      document.title = `${currentNav.title} | ${displayName}`
    } else {
      document.title = displayName
    }
  }, [location.pathname, displayName])

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
      // Close WebSocket if open - only if OPEN (CONNECTING will close in onopen)
      if (blockingLogsWsRef.current && blockingLogsWsRef.current.readyState === WebSocket.OPEN) {
        blockingLogsWsRef.current.close()
      }
      blockingLogsWsRef.current = null
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

      let shouldConnect = true

      // Don't interrupt an existing connection that's still connecting
      if (blockingLogsWsRef.current) {
        if (blockingLogsWsRef.current.readyState === WebSocket.CONNECTING) {
          return // Already connecting, wait for it
        }
        if (blockingLogsWsRef.current.readyState === WebSocket.OPEN) {
          blockingLogsWsRef.current.close()
        }
        blockingLogsWsRef.current = null
      }

      const ws = new WebSocket(apiClient.getWebSocketUrl('/ws/logs'))
      // Assign to ref IMMEDIATELY so concurrent calls see it's connecting
      blockingLogsWsRef.current = ws

      ws.onopen = () => {
        if (!shouldConnect) {
          // Effect cleanup ran while connecting - close now
          ws.close()
        }
      }

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

      return () => {
        shouldConnect = false
        // Only close if already OPEN - CONNECTING WebSockets will close in onopen
        if (ws.readyState === WebSocket.OPEN) {
          ws.close()
        }
        blockingLogsWsRef.current = null
      }
    }

    // If backend disconnected, show connection retry logs
    if (!isBackendConnected) {
      addLog('INFO', `Attempting to connect to backend at ${window.location.host}...`)

      const interval = setInterval(() => {
        addLog('INFO', `Retrying connection to WebSocket /ws/status...`)

        apiClient.get('/api/settings')
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
    let shouldConnect = true

    const connectCacheWebSocket = () => {
      if (!shouldConnect) return
      // Don't interrupt an existing connection that's still connecting
      if (cacheWsRef.current) {
        if (cacheWsRef.current.readyState === WebSocket.CONNECTING) {
          return // Already connecting, wait for it
        }
        if (cacheWsRef.current.readyState === WebSocket.OPEN) {
          return // Already connected
        }
        // CLOSING or CLOSED state - clear the ref
        cacheWsRef.current = null
      }

      const ws = new WebSocket(apiClient.getWebSocketUrl('/ws/cache-progress'))
      // Assign to ref IMMEDIATELY so concurrent calls see it's connecting
      cacheWsRef.current = ws

      ws.onopen = () => {
        if (!shouldConnect) {
          // Effect cleanup ran while connecting - close now
          ws.close()
        }
      }

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
        if (!shouldConnect) return
        cacheWsRef.current = null
        // Reconnect after 3 seconds
        if (shouldConnect && isBackendConnected) {
          reconnectTimeout = setTimeout(connectCacheWebSocket, 3000)
        }
      }

      ws.onerror = () => {
        // Will trigger onclose
      }
    }

    connectCacheWebSocket()

    return () => {
      shouldConnect = false
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout)
      }
      if (cacheWsRef.current) {
        // Only close if already OPEN - CONNECTING WebSockets will close in onopen
        if (cacheWsRef.current.readyState === WebSocket.OPEN) {
          cacheWsRef.current.close()
        }
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

  // Now Playing button drag handlers
  const getSnapPositions = useCallback(() => {
    const padding = 16
    const buttonWidth = buttonRef.current?.offsetWidth || 140
    return {
      left: padding + buttonWidth / 2,
      center: window.innerWidth / 2,
      right: window.innerWidth - padding - buttonWidth / 2,
    }
  }, [])

  const handleButtonDragStart = useCallback((clientX: number, clientY: number) => {
    if (!buttonRef.current) return
    const rect = buttonRef.current.getBoundingClientRect()
    const buttonCenterX = rect.left + rect.width / 2
    dragStartRef.current = { x: clientX, y: clientY, buttonX: buttonCenterX }
    wasDraggingRef.current = false // Reset drag flag
    setIsDraggingButton(true)
    setDragOffset({ x: 0, y: 0 })
  }, [])

  const handleButtonDragMove = useCallback((clientX: number) => {
    if (!dragStartRef.current || !isDraggingButton) return
    const deltaX = clientX - dragStartRef.current.x
    // Mark as dragging if moved more than 8px (to distinguish from clicks)
    if (Math.abs(deltaX) > 8) {
      wasDraggingRef.current = true
    }
    setDragOffset({ x: deltaX, y: 0 })
  }, [isDraggingButton])

  const handleButtonDragEnd = useCallback(() => {
    if (!dragStartRef.current || !buttonRef.current) {
      setIsDraggingButton(false)
      setDragOffset({ x: 0, y: 0 })
      return
    }

    // Calculate current position
    const currentX = dragStartRef.current.buttonX + dragOffset.x
    const snapPositions = getSnapPositions()

    // Find nearest snap position
    const distances = {
      left: Math.abs(currentX - snapPositions.left),
      center: Math.abs(currentX - snapPositions.center),
      right: Math.abs(currentX - snapPositions.right),
    }

    let nearest: SnapPosition = 'center'
    let minDistance = distances.center
    if (distances.left < minDistance) {
      nearest = 'left'
      minDistance = distances.left
    }
    if (distances.right < minDistance) {
      nearest = 'right'
    }

    // Update position and persist
    setNowPlayingButtonPos(nearest)
    localStorage.setItem('nowPlayingButtonPos', nearest)

    // Reset drag state
    setIsDraggingButton(false)
    setDragOffset({ x: 0, y: 0 })
    dragStartRef.current = null
  }, [dragOffset.x, getSnapPositions])

  // Mouse drag handlers
  useEffect(() => {
    if (!isDraggingButton) return

    const handleMouseMove = (e: MouseEvent) => {
      e.preventDefault()
      handleButtonDragMove(e.clientX)
    }

    const handleMouseUp = () => {
      handleButtonDragEnd()
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)

    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isDraggingButton, handleButtonDragMove, handleButtonDragEnd])

  // Get button position style
  const getButtonPositionStyle = useCallback((): React.CSSProperties => {
    const baseStyle: React.CSSProperties = {
      bottom: 'calc(4.5rem + env(safe-area-inset-bottom, 0px))',
    }

    if (isDraggingButton && dragStartRef.current) {
      // During drag, use transform for smooth movement
      const snapPositions = getSnapPositions()
      const startX = snapPositions[nowPlayingButtonPos]
      return {
        ...baseStyle,
        left: startX,
        transform: `translateX(calc(-50% + ${dragOffset.x}px))`,
        transition: 'none',
        cursor: 'grabbing',
      }
    }

    // Snapped positions
    switch (nowPlayingButtonPos) {
      case 'left':
        return { ...baseStyle, left: '1rem', transform: 'translateX(0)' }
      case 'right':
        return { ...baseStyle, right: '1rem', left: 'auto', transform: 'translateX(0)' }
      case 'center':
      default:
        return { ...baseStyle, left: '50%', transform: 'translateX(-50%)' }
    }
  }, [isDraggingButton, dragOffset.x, nowPlayingButtonPos, getSnapPositions])

  const cacheAllPercentage = cacheAllProgress?.total
    ? Math.round((cacheAllProgress.completed / cacheAllProgress.total) * 100)
    : 0

  return (
    <div className="min-h-dvh bg-background flex flex-col">
      {/* Sensor Homing Failure Popup */}
      {sensorHomingFailed && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-background rounded-lg shadow-xl w-full max-w-md border border-destructive/30">
            <div className="p-6">
              <div className="text-center space-y-4">
                <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-destructive/10 mb-2">
                  <span className="material-icons-outlined text-4xl text-destructive">
                    error_outline
                  </span>
                </div>
                <h2 className="text-xl font-semibold">Sensor Homing Failed</h2>
                <p className="text-muted-foreground text-sm">
                  The sensor homing process could not complete. The limit sensors may not be positioned correctly or may be malfunctioning.
                </p>

                <div className="bg-amber-500/10 border border-amber-500/20 p-3 rounded-lg text-sm text-left">
                  <p className="text-amber-600 dark:text-amber-400 font-medium mb-2">
                    Troubleshooting steps:
                  </p>
                  <ul className="text-amber-600 dark:text-amber-400 space-y-1 list-disc list-inside">
                    <li>Check that the limit sensors are properly connected</li>
                    <li>Verify the sensor positions are correct</li>
                    <li>Ensure nothing is blocking the sensor path</li>
                    <li>Check for loose wiring connections</li>
                  </ul>
                </div>

                <p className="text-muted-foreground text-sm">
                  Connection will not be established until this is resolved.
                </p>

                {/* Action Buttons */}
                {!isRecoveringHoming ? (
                  <div className="flex flex-col gap-2 pt-2">
                    <Button
                      onClick={() => handleSensorHomingRecovery(false)}
                      className="w-full gap-2"
                    >
                      <span className="material-icons text-base">refresh</span>
                      Retry Sensor Homing
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => handleSensorHomingRecovery(true)}
                      className="w-full gap-2"
                    >
                      <span className="material-icons text-base">sync_alt</span>
                      Switch to Crash Homing
                    </Button>
                    <p className="text-xs text-muted-foreground">
                      Crash homing moves the arm to a physical stop without using sensors.
                    </p>
                  </div>
                ) : (
                  <div className="flex items-center justify-center gap-2 py-4">
                    <span className="material-icons-outlined text-primary animate-spin">sync</span>
                    <span className="text-muted-foreground">Attempting recovery...</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

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
                    <Button variant="secondary" onClick={handleCacheAllPreviews} className="gap-2">
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
      {/* Don't show this overlay when sensor homing failed - that has its own dialog */}
      {!sensorHomingFailed && (!isBackendConnected || (isHoming && !homingDismissed) || homingJustCompleted) && (
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
                      copyToClipboard(logText)
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
                      variant="secondary"
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

            {/* Dismiss button during homing */}
            {isHoming && !homingJustCompleted && (
              <div className="flex justify-center">
                <Button
                  variant="ghost"
                  onClick={() => setHomingDismissed(true)}
                  className="gap-2 text-muted-foreground"
                >
                  <span className="material-icons text-base">visibility_off</span>
                  Dismiss
                </Button>
              </div>
            )}

            {/* Hint */}
            {!homingJustCompleted && (
              <p className="text-center text-xs text-muted-foreground">
                {isHoming
                  ? 'Homing will continue in the background'
                  : 'Make sure the backend server is running on port 8080'
                }
              </p>
            )}
          </div>
        </div>
      )}

      {/* Header - Floating Pill */}
      <header className="fixed top-0 left-0 right-0 z-40 pt-safe">
        {/* Blurry backdrop behind header - only on Browse page where content scrolls under */}
        {location.pathname === '/' && (
          <div className="absolute inset-0 bg-background/80 backdrop-blur-md supports-[backdrop-filter]:bg-background/50" style={{ height: 'calc(5rem + env(safe-area-inset-top, 0px))' }} />
        )}
        <div className="relative w-full max-w-5xl mx-auto px-3 sm:px-4 pt-3 pointer-events-none">
          <div className="flex h-12 items-center justify-between px-4 rounded-full bg-card shadow-lg border border-border pointer-events-auto">
          <div className="flex items-center gap-2">
            <Link to="/">
              <img
                src={customLogo ? apiClient.getAssetUrl(`/static/custom/${customLogo}`) : apiClient.getAssetUrl('/static/android-chrome-192x192.png')}
                alt={displayName}
                className="w-8 h-8 rounded-full object-cover"
              />
            </Link>
            <TableSelector>
              <button className="flex items-center gap-1.5 hover:opacity-80 transition-opacity group">
                <ShinyText
                  text={displayName}
                  className="font-semibold text-lg"
                  speed={4}
                  color={isDark ? '#a8a8a8' : '#555555'}
                  shineColor={isDark ? '#ffffff' : '#999999'}
                  spread={75}
                />
                <span className="material-icons-outlined text-muted-foreground text-sm group-hover:text-foreground transition-colors">
                  expand_more
                </span>
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
              </button>
            </TableSelector>
          </div>

          {/* Desktop actions */}
          <div className="hidden md:flex items-center gap-0 ml-2">
            {updateAvailable && (
              <Link to="/settings?section=version" title="Software update available">
                <span className="relative flex items-center justify-center w-8 h-8 rounded-full hover:bg-accent transition-colors">
                  <span className="material-icons-outlined text-xl">download</span>
                  <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                </span>
              </Link>
            )}
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="rounded-full"
                  aria-label="Open menu"
                >
                  <span className="material-icons-outlined">menu</span>
                </Button>
              </PopoverTrigger>
              <PopoverContent align="end" className="w-56 p-2">
                <div className="flex flex-col gap-1">
                  <button
                    onClick={() => setIsDark(!isDark)}
                    className="flex items-center gap-3 w-full px-3 py-2 text-sm rounded-md hover:bg-accent transition-colors"
                  >
                    <span className="material-icons-outlined text-xl">
                      {isDark ? 'light_mode' : 'dark_mode'}
                    </span>
                    {isDark ? 'Light Mode' : 'Dark Mode'}
                  </button>
                  <button
                    onClick={handleToggleLogs}
                    className="flex items-center gap-3 w-full px-3 py-2 text-sm rounded-md hover:bg-accent transition-colors"
                  >
                    <span className="material-icons-outlined text-xl">article</span>
                    View Logs
                  </button>
                  <Separator className="my-1" />
                  <button
                    onClick={handleRestart}
                    className="flex items-center gap-3 w-full px-3 py-2 text-sm rounded-md hover:bg-accent transition-colors text-amber-500"
                  >
                    <span className="material-icons-outlined text-xl">restart_alt</span>
                    Restart Docker
                  </button>
                  <button
                    onClick={handleShutdown}
                    className="flex items-center gap-3 w-full px-3 py-2 text-sm rounded-md hover:bg-accent transition-colors text-red-500"
                  >
                    <span className="material-icons-outlined text-xl">power_settings_new</span>
                    Shutdown
                  </button>
                </div>
              </PopoverContent>
            </Popover>
          </div>

          {/* Mobile actions */}
          <div className="flex md:hidden items-center gap-0 ml-2">
            {updateAvailable && (
              <Link to="/settings?section=version" title="Software update available">
                <span className="relative flex items-center justify-center w-8 h-8 rounded-full hover:bg-accent transition-colors">
                  <span className="material-icons-outlined text-xl">download</span>
                  <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                </span>
              </Link>
            )}
            <Popover open={isMobileMenuOpen} onOpenChange={setIsMobileMenuOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="rounded-full"
                  aria-label="Open menu"
                >
                  <span className="material-icons-outlined">
                    {isMobileMenuOpen ? 'close' : 'menu'}
                  </span>
                </Button>
              </PopoverTrigger>
              <PopoverContent align="end" className="w-56 p-2">
                <div className="flex flex-col gap-1">
                  <button
                    onClick={() => {
                      setIsDark(!isDark)
                      setIsMobileMenuOpen(false)
                    }}
                    className="flex items-center gap-3 w-full px-3 py-2 text-sm rounded-md hover:bg-accent transition-colors"
                  >
                    <span className="material-icons-outlined text-xl">
                      {isDark ? 'light_mode' : 'dark_mode'}
                    </span>
                    {isDark ? 'Light Mode' : 'Dark Mode'}
                  </button>
                  <button
                    onClick={() => {
                      handleToggleLogs()
                      setIsMobileMenuOpen(false)
                    }}
                    className="flex items-center gap-3 w-full px-3 py-2 text-sm rounded-md hover:bg-accent transition-colors"
                  >
                    <span className="material-icons-outlined text-xl">article</span>
                    View Logs
                  </button>
                  <Separator className="my-1" />
                  <button
                    onClick={() => {
                      handleRestart()
                      setIsMobileMenuOpen(false)
                    }}
                    className="flex items-center gap-3 w-full px-3 py-2 text-sm rounded-md hover:bg-accent transition-colors text-amber-500"
                  >
                    <span className="material-icons-outlined text-xl">restart_alt</span>
                    Restart Docker
                  </button>
                  <button
                    onClick={() => {
                      handleShutdown()
                      setIsMobileMenuOpen(false)
                    }}
                    className="flex items-center gap-3 w-full px-3 py-2 text-sm rounded-md hover:bg-accent transition-colors text-red-500"
                  >
                    <span className="material-icons-outlined text-xl">power_settings_new</span>
                    Shutdown
                  </button>
                </div>
              </PopoverContent>
            </Popover>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main
        className="container mx-auto px-4 transition-all duration-300"
        style={{
          paddingTop: 'calc(4.5rem + env(safe-area-inset-top, 0px))',
          paddingBottom: isLogsOpen
            ? isNowPlayingOpen
              ? `calc(${logsDrawerHeight + 256 + 64}px + env(safe-area-inset-bottom, 0px))` // drawer + now playing + nav + safe area
              : `calc(${logsDrawerHeight + 64}px + env(safe-area-inset-bottom, 0px))` // drawer + nav + safe area
            : isNowPlayingOpen
              ? 'calc(20rem + env(safe-area-inset-bottom, 0px))' // now playing bar + nav + safe area
              : 'calc(8rem + env(safe-area-inset-bottom, 0px))' // floating pill + nav + safe area
        }}
      >
        <Outlet />
      </main>

      {/* Now Playing Bar */}
      <NowPlayingBar
        isLogsOpen={isLogsOpen}
        logsDrawerHeight={logsDrawerHeight}
        isVisible={isNowPlayingOpen}
        openExpanded={openNowPlayingExpanded}
        onClose={() => setIsNowPlayingOpen(false)}
      />


      {/* Logs Drawer */}
      <div
        className={`fixed left-0 right-0 z-30 bg-background border-t border-border ${
          isResizing ? '' : 'transition-[height] duration-300'
        }`}
        style={{
          height: isLogsOpen ? logsDrawerHeight : 0,
          bottom: 'calc(4rem + env(safe-area-inset-bottom, 0px))'
        }}
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

            {/* Logs Header */}
            <div className="flex items-center justify-between px-4 py-2 border-b bg-muted/50 gap-2">
              <div className="flex items-center gap-2 sm:gap-3 flex-wrap min-w-0">
                <span className="text-sm font-medium whitespace-nowrap">Application Logs</span>
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
                <input
                  type="text"
                  value={logSearchQuery}
                  onChange={(e) => setLogSearchQuery(e.target.value)}
                  placeholder="Search logs..."
                  className="text-xs bg-background border rounded px-2 py-1 w-28 sm:w-40"
                />
                {logSearchQuery && (
                  <Button variant="ghost" size="icon-sm" onClick={() => setLogSearchQuery('')} className="rounded-full" title="Clear search">
                    <span className="material-icons-outlined text-sm">close</span>
                  </Button>
                )}
                <span className="text-xs text-muted-foreground">
                  {filteredLogs.length}{logsTotal > 0 ? ` of ${logsTotal}` : ''} entries
                  {logsHasMore && <span className="text-primary ml-1">↑ scroll for more</span>}
                </span>
              </div>

              <div className="flex items-center gap-1 shrink-0">
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
                  title="Close"
                >
                  <span className="material-icons-outlined text-base">close</span>
                </Button>
              </div>
            </div>

            {/* Logs Content */}
            <div
              ref={logsContainerRef}
              className="h-[calc(100%-40px)] overflow-auto overscroll-contain p-3 font-mono text-xs space-y-0.5"
            >
              {/* Loading indicator for older logs */}
              {isLoadingMoreLogs && (
                <div className="flex items-center justify-center gap-2 py-2 text-muted-foreground">
                  <span className="material-icons-outlined text-sm animate-spin">sync</span>
                  <span>Loading older logs...</span>
                </div>
              )}
              {/* Load more hint */}
              {logsHasMore && !isLoadingMoreLogs && (
                <div className="text-center py-2 text-muted-foreground text-xs">
                  ↑ Scroll up to load older logs
                </div>
              )}
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

      {/* Floating Now Playing Button - draggable, snaps to left/center/right */}
      {!isNowPlayingOpen && (
        <button
          ref={buttonRef}
          onClick={() => {
            // Only open if it wasn't a drag (to distinguish click from drag)
            if (!wasDraggingRef.current) {
              setIsNowPlayingOpen(true)
            }
            wasDraggingRef.current = false
          }}
          onMouseDown={(e) => {
            e.preventDefault()
            handleButtonDragStart(e.clientX, e.clientY)
          }}
          onTouchStart={(e) => {
            const touch = e.touches[0]
            handleButtonDragStart(touch.clientX, touch.clientY)
          }}
          onTouchMove={(e) => {
            const touch = e.touches[0]
            handleButtonDragMove(touch.clientX)
          }}
          onTouchEnd={() => {
            handleButtonDragEnd()
          }}
          className={`fixed z-40 flex items-center gap-2 px-4 py-2 rounded-full bg-card border border-border shadow-lg select-none touch-none ${
            isDraggingButton
              ? 'cursor-grabbing scale-105 shadow-xl'
              : 'cursor-grab transition-all duration-300 hover:shadow-xl hover:scale-105 active:scale-95'
          }`}
          style={getButtonPositionStyle()}
          aria-label={isCurrentlyPlaying ? 'Now Playing' : 'Not Playing'}
        >
          <span className={`material-icons-outlined text-xl ${isCurrentlyPlaying ? 'text-primary' : 'text-muted-foreground'}`}>
            {isCurrentlyPlaying ? 'play_circle' : 'stop_circle'}
          </span>
          <span className="text-sm font-medium">
            {isCurrentlyPlaying ? 'Now Playing' : 'Not Playing'}
          </span>
        </button>
      )}

      {/* Bottom Navigation */}
      <nav className="fixed bottom-0 left-0 right-0 z-40 border-t border-border bg-card pb-safe">
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
