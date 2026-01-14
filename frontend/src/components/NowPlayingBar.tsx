import { useState, useEffect, useRef, useCallback } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Input } from '@/components/ui/input'
import { apiClient } from '@/lib/apiClient'

type Coordinate = [number, number]

interface PlaybackStatus {
  current_file: string | null
  is_paused: boolean
  manual_pause: boolean
  scheduled_pause: boolean
  is_running: boolean
  progress: {
    current: number
    total: number
    remaining_time: number
    elapsed_time: number
    percentage: number
  } | null
  playlist: {
    current_index: number
    total_files: number
    mode: string
    next_file: string | null
  } | null
  speed: number
  pause_time_remaining: number
  original_pause_time: number | null
  connection_status: boolean
  current_theta: number
  current_rho: number
}

function formatTime(seconds: number): string {
  if (!seconds || seconds < 0) return '--:--'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

function formatPatternName(path: string | null): string {
  if (!path) return 'Unknown'
  // Extract filename without extension and path
  const name = path.split('/').pop()?.replace('.thr', '') || path
  return name
}

interface NowPlayingBarProps {
  isLogsOpen?: boolean
  isVisible: boolean
  openExpanded?: boolean
  onClose: () => void
}

export function NowPlayingBar({ isLogsOpen = false, isVisible, openExpanded = false, onClose }: NowPlayingBarProps) {
  const [status, setStatus] = useState<PlaybackStatus | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  // Expanded state for slide-up view
  const [isExpanded, setIsExpanded] = useState(false)

  // Swipe gesture handling
  const touchStartY = useRef<number | null>(null)
  const barRef = useRef<HTMLDivElement>(null)

  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartY.current = e.touches[0].clientY
  }
  const handleTouchEnd = (e: React.TouchEvent) => {
    if (touchStartY.current === null) return
    const touchEndY = e.changedTouches[0].clientY
    const deltaY = touchEndY - touchStartY.current

    if (deltaY > 50) {
      // Swipe down
      if (isExpanded) {
        setIsExpanded(false) // Collapse to mini
      } else {
        onClose() // Hide the bar
      }
    } else if (deltaY < -50 && isPlaying) {
      // Swipe up - expand (only if playing)
      setIsExpanded(true)
    }
    touchStartY.current = null
  }

  // Use native event listener for touchmove to prevent background scroll
  useEffect(() => {
    const bar = barRef.current
    if (!bar) return

    const handleTouchMove = (e: TouchEvent) => {
      e.preventDefault()
    }

    bar.addEventListener('touchmove', handleTouchMove, { passive: false })
    return () => {
      bar.removeEventListener('touchmove', handleTouchMove)
    }
  }, [])

  // Open in expanded mode when openExpanded prop changes to true
  useEffect(() => {
    if (openExpanded && isVisible) {
      setIsExpanded(true)
    }
  }, [openExpanded, isVisible])

  // Listen for playback-started event from Layout (more reliable than prop)
  useEffect(() => {
    const handlePlaybackStarted = () => {
      setIsExpanded(true)
    }
    window.addEventListener('playback-started', handlePlaybackStarted)
    return () => window.removeEventListener('playback-started', handlePlaybackStarted)
  }, [])

  // Auto-collapse when nothing is playing (with delay to avoid race condition)
  const isPlaying = status?.is_running || status?.is_paused
  const collapseTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    // Clear any pending collapse
    if (collapseTimeoutRef.current) {
      clearTimeout(collapseTimeoutRef.current)
      collapseTimeoutRef.current = null
    }

    if (!isPlaying && isExpanded) {
      // Delay collapse to avoid race condition with playback-started
      collapseTimeoutRef.current = setTimeout(() => {
        setIsExpanded(false)
      }, 500)
    }

    return () => {
      if (collapseTimeoutRef.current) {
        clearTimeout(collapseTimeoutRef.current)
      }
    }
  }, [isPlaying, isExpanded])

  const [coordinates, setCoordinates] = useState<Coordinate[]>([])
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const offscreenCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const lastDrawnIndexRef = useRef<number>(-1)
  const lastFileRef = useRef<string | null>(null)
  const lastThemeRef = useRef<boolean | null>(null)

  // Smooth animation refs
  const animationFrameRef = useRef<number | null>(null)
  const lastProgressRef = useRef<number>(0)
  const lastProgressTimeRef = useRef<number>(0)
  const smoothProgressRef = useRef<number>(0)

  // Connect to status WebSocket (reconnects when table changes)
  useEffect(() => {
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null
    let shouldReconnect = true

    const connectWebSocket = () => {
      if (!shouldReconnect) return

      const wsUrl = apiClient.getWebSocketUrl('/ws/status')
      const ws = new WebSocket(wsUrl)

      ws.onmessage = (event) => {
        if (!shouldReconnect) return
        try {
          const message = JSON.parse(event.data)
          if (message.type === 'status_update' && message.data) {
            setStatus(message.data)
          }
        } catch {
          // Ignore parse errors
        }
      }

      ws.onclose = () => {
        if (!shouldReconnect) return
        reconnectTimeout = setTimeout(connectWebSocket, 3000)
      }

      wsRef.current = ws
    }

    connectWebSocket()

    // Reconnect when base URL changes (table switch)
    const unsubscribe = apiClient.onBaseUrlChange(() => {
      // Disable reconnect for old connection
      shouldReconnect = false
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout)
        reconnectTimeout = null
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
      // Re-enable and connect to new URL
      shouldReconnect = true
      connectWebSocket()
    })

    return () => {
      shouldReconnect = false
      unsubscribe()
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [])

  // Fetch preview images for current and next patterns
  const [nextPreviewUrl, setNextPreviewUrl] = useState<string | null>(null)
  const lastFetchedFilesRef = useRef<string>('')

  useEffect(() => {
    // Don't fetch if not visible
    if (!isVisible) return

    const currentFile = status?.current_file
    const nextFile = status?.playlist?.next_file

    // Build list of files to fetch
    const filesToFetch = [currentFile, nextFile].filter(Boolean) as string[]
    const fetchKey = filesToFetch.join('|')

    // Skip if we already fetched these exact files
    if (fetchKey === lastFetchedFilesRef.current) return
    lastFetchedFilesRef.current = fetchKey

    if (filesToFetch.length > 0) {
      apiClient.post<Record<string, { image_data?: string }>>('/preview_thr_batch', { file_names: filesToFetch })
        .then((data) => {
          if (currentFile && data[currentFile]?.image_data) {
            setPreviewUrl(data[currentFile].image_data)
          } else {
            setPreviewUrl(null)
          }
          if (nextFile && data[nextFile]?.image_data) {
            setNextPreviewUrl(data[nextFile].image_data)
          } else {
            setNextPreviewUrl(null)
          }
        })
        .catch(() => {
          setPreviewUrl(null)
          setNextPreviewUrl(null)
        })
    } else {
      setPreviewUrl(null)
      setNextPreviewUrl(null)
    }
  }, [isVisible, status?.current_file, status?.playlist?.next_file])

  // Canvas drawing functions for real-time preview
  const polarToCartesian = useCallback((theta: number, rho: number, size: number) => {
    const centerX = size / 2
    const centerY = size / 2
    const radius = (size / 2) * 0.9 * rho
    const x = centerX + radius * Math.cos(theta)
    const y = centerY + radius * Math.sin(theta)
    return { x, y }
  }, [])

  const getThemeColors = useCallback(() => {
    const isDark = document.documentElement.classList.contains('dark')
    return {
      isDark,
      bgOuter: isDark ? '#1a1a1a' : '#f5f5f5',
      bgInner: isDark ? '#262626' : '#ffffff',
      borderColor: isDark ? 'rgba(255, 255, 255, 0.2)' : 'rgba(128, 128, 128, 0.3)',
      lineColor: isDark ? '#e5e5e5' : '#333333',
      markerBorder: isDark ? '#333333' : '#ffffff',
    }
  }, [])

  const initOffscreenCanvas = useCallback((size: number, coords: Coordinate[]) => {
    const colors = getThemeColors()

    if (!offscreenCanvasRef.current) {
      offscreenCanvasRef.current = document.createElement('canvas')
    }

    const offscreen = offscreenCanvasRef.current
    offscreen.width = size
    offscreen.height = size

    const ctx = offscreen.getContext('2d')
    if (!ctx) return

    ctx.fillStyle = colors.bgOuter
    ctx.fillRect(0, 0, size, size)

    ctx.beginPath()
    ctx.arc(size / 2, size / 2, (size / 2) * 0.95, 0, Math.PI * 2)
    ctx.fillStyle = colors.bgInner
    ctx.fill()
    ctx.strokeStyle = colors.borderColor
    ctx.lineWidth = 1
    ctx.stroke()

    ctx.strokeStyle = colors.lineColor
    ctx.lineWidth = 1.5
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'

    if (coords.length > 0) {
      const firstPoint = polarToCartesian(coords[0][0], coords[0][1], size)
      ctx.beginPath()
      ctx.moveTo(firstPoint.x, firstPoint.y)
      ctx.stroke()
    }

    lastDrawnIndexRef.current = 0
    lastThemeRef.current = colors.isDark
  }, [getThemeColors, polarToCartesian])

  const drawPattern = useCallback((ctx: CanvasRenderingContext2D, coords: Coordinate[], smoothIndex: number, forceRedraw = false) => {
    const canvas = ctx.canvas
    const size = canvas.width
    const colors = getThemeColors()

    // Apply 16 coordinate offset for physical latency
    const adjustedSmoothIndex = Math.max(0, smoothIndex - 16)
    const adjustedIndex = Math.floor(adjustedSmoothIndex)

    const needsReinit = forceRedraw ||
      !offscreenCanvasRef.current ||
      lastThemeRef.current !== colors.isDark ||
      adjustedIndex < lastDrawnIndexRef.current

    if (needsReinit) {
      initOffscreenCanvas(size, coords)
    }

    const offscreen = offscreenCanvasRef.current
    if (!offscreen) return

    const offCtx = offscreen.getContext('2d')
    if (!offCtx) return

    if (coords.length > 0 && adjustedIndex > lastDrawnIndexRef.current) {
      offCtx.strokeStyle = colors.lineColor
      offCtx.lineWidth = 1.5
      offCtx.lineCap = 'round'
      offCtx.lineJoin = 'round'

      offCtx.beginPath()
      const startPoint = polarToCartesian(
        coords[lastDrawnIndexRef.current][0],
        coords[lastDrawnIndexRef.current][1],
        size
      )
      offCtx.moveTo(startPoint.x, startPoint.y)

      for (let i = lastDrawnIndexRef.current + 1; i <= adjustedIndex && i < coords.length; i++) {
        const point = polarToCartesian(coords[i][0], coords[i][1], size)
        offCtx.lineTo(point.x, point.y)
      }
      offCtx.stroke()

      lastDrawnIndexRef.current = adjustedIndex
    }

    ctx.drawImage(offscreen, 0, 0)

    // Draw current position marker with smooth interpolation between coordinates
    if (coords.length > 0 && adjustedIndex < coords.length - 1) {
      const fraction = adjustedSmoothIndex - adjustedIndex
      const currentCoord = coords[adjustedIndex]
      const nextCoord = coords[Math.min(adjustedIndex + 1, coords.length - 1)]

      // Interpolate theta and rho
      const interpTheta = currentCoord[0] + (nextCoord[0] - currentCoord[0]) * fraction
      const interpRho = currentCoord[1] + (nextCoord[1] - currentCoord[1]) * fraction

      const currentPoint = polarToCartesian(interpTheta, interpRho, size)
      ctx.beginPath()
      ctx.arc(currentPoint.x, currentPoint.y, 8, 0, Math.PI * 2)
      ctx.fillStyle = '#0b80ee'
      ctx.fill()
      ctx.strokeStyle = colors.markerBorder
      ctx.lineWidth = 2
      ctx.stroke()
    } else if (coords.length > 0 && adjustedIndex < coords.length) {
      // At the last coordinate, just draw without interpolation
      const currentPoint = polarToCartesian(coords[adjustedIndex][0], coords[adjustedIndex][1], size)
      ctx.beginPath()
      ctx.arc(currentPoint.x, currentPoint.y, 8, 0, Math.PI * 2)
      ctx.fillStyle = '#0b80ee'
      ctx.fill()
      ctx.strokeStyle = colors.markerBorder
      ctx.lineWidth = 2
      ctx.stroke()
    }
  }, [getThemeColors, initOffscreenCanvas, polarToCartesian])

  // Fetch coordinates when file changes or fullscreen opens
  useEffect(() => {
    const currentFile = status?.current_file
    if (!currentFile) return

    // Only fetch if file changed or we don't have coordinates yet
    const needsFetch = currentFile !== lastFileRef.current || coordinates.length === 0

    if (!needsFetch) return

    lastFileRef.current = currentFile
    lastDrawnIndexRef.current = -1

    apiClient.post<{ coordinates?: Coordinate[] }>('/get_theta_rho_coordinates', { file_name: currentFile })
      .then((data) => {
        if (data.coordinates && Array.isArray(data.coordinates)) {
          setCoordinates(data.coordinates)
        }
      })
      .catch((err) => {
        console.error('Failed to fetch coordinates:', err)
        setCoordinates([])
      })
  }, [status?.current_file, coordinates.length])

  // Get target index from progress percentage
  const getTargetIndex = useCallback((coords: Coordinate[]): number => {
    if (coords.length === 0) return 0
    const progressPercent = status?.progress?.percentage || 0
    return (progressPercent / 100) * coords.length
  }, [status?.progress?.percentage])

  // Track progress updates for smooth interpolation
  useEffect(() => {
    const currentProgress = status?.progress?.percentage || 0
    if (currentProgress !== lastProgressRef.current) {
      lastProgressRef.current = currentProgress
      lastProgressTimeRef.current = performance.now()
    }
  }, [status?.progress?.percentage])

  // Smooth animation loop
  useEffect(() => {
    if (!isExpanded || coordinates.length === 0) return

    const isPaused = status?.is_paused || false
    const coordsPerSecond = 4.2

    const animate = () => {
      if (!canvasRef.current) return

      const ctx = canvasRef.current.getContext('2d')
      if (!ctx) return

      const targetIndex = getTargetIndex(coordinates)
      const now = performance.now()
      const timeSinceUpdate = (now - lastProgressTimeRef.current) / 1000

      let smoothIndex: number
      if (isPaused) {
        // When paused, just use the target index directly
        smoothIndex = targetIndex
      } else {
        // Interpolate: start from where we were at last update, advance based on time
        const baseIndex = (lastProgressRef.current / 100) * coordinates.length
        smoothIndex = baseIndex + (timeSinceUpdate * coordsPerSecond)
        // Don't overshoot the target too much
        smoothIndex = Math.min(smoothIndex, targetIndex + 2)
      }

      smoothProgressRef.current = smoothIndex
      drawPattern(ctx, coordinates, smoothIndex)

      animationFrameRef.current = requestAnimationFrame(animate)
    }

    // Initial draw with force redraw
    const timer = setTimeout(() => {
      if (!canvasRef.current) return
      const ctx = canvasRef.current.getContext('2d')
      if (!ctx) return

      lastDrawnIndexRef.current = -1
      offscreenCanvasRef.current = null
      smoothProgressRef.current = getTargetIndex(coordinates)
      lastProgressTimeRef.current = performance.now()

      drawPattern(ctx, coordinates, smoothProgressRef.current, true)

      // Start animation loop
      animationFrameRef.current = requestAnimationFrame(animate)
    }, 50)

    return () => {
      clearTimeout(timer)
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current)
      }
    }
  }, [isExpanded, coordinates, status?.is_paused, drawPattern, getTargetIndex])

  const handlePause = async () => {
    try {
      const endpoint = status?.is_paused ? '/resume_execution' : '/pause_execution'
      await apiClient.post(endpoint)
      toast.success(status?.is_paused ? 'Resumed' : 'Paused')
    } catch {
      toast.error('Failed to toggle pause')
    }
  }

  const handleStop = async () => {
    try {
      await apiClient.post('/stop_execution')
      toast.success('Stopped')
    } catch {
      toast.error('Failed to stop')
    }
  }

  const handleSkip = async () => {
    try {
      await apiClient.post('/skip_pattern')
      toast.success('Skipping to next pattern')
    } catch {
      toast.error('Failed to skip')
    }
  }

  const [speedInput, setSpeedInput] = useState('')

  const handleSpeedSubmit = async () => {
    const speed = parseInt(speedInput)
    if (isNaN(speed) || speed < 100 || speed > 6000) {
      toast.error('Speed must be between 100 and 6000 mm/s')
      return
    }
    try {
      await apiClient.post('/set_speed', { speed })
      setSpeedInput('')
      toast.success(`Speed set to ${speed} mm/s`)
    } catch {
      toast.error('Failed to set speed')
    }
  }

  // Don't render if not visible
  if (!isVisible) {
    return null
  }

  const patternName = formatPatternName(status?.current_file ?? null)
  const progressPercent = status?.progress?.percentage || 0
  const remainingTime = status?.progress?.remaining_time || 0
  const elapsedTime = status?.progress?.elapsed_time || 0

  return (
    <>
      {/* Backdrop when expanded */}
      {isExpanded && (
        <div
          className="fixed inset-0 bg-black/30 z-30"
          onClick={() => setIsExpanded(false)}
        />
      )}

      {/* Now Playing Bar - slides up to full height on mobile, 50vh on desktop when expanded */}
      <div
        ref={barRef}
        className="fixed left-0 right-0 z-40 bg-background border-t shadow-lg transition-all duration-300"
        style={{
          bottom: isLogsOpen
            ? 'calc(20rem + env(safe-area-inset-bottom, 0px))'
            : 'calc(4rem + env(safe-area-inset-bottom, 0px))'
        }}
        data-now-playing-bar={isExpanded ? 'expanded' : 'collapsed'}
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
      >
        {/* Swipe indicator - only on mobile */}
        <div className="md:hidden flex justify-center pt-2 pb-1">
          <div className="w-10 h-1 bg-muted-foreground/30 rounded-full" />
        </div>

        {/* Header with action buttons */}
        <div className="absolute top-3 right-3 flex items-center gap-1 z-10">
          {isPlaying && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setIsExpanded(!isExpanded)}
              title={isExpanded ? 'Collapse' : 'Expand'}
            >
              <span className="material-icons-outlined text-lg">
                {isExpanded ? 'expand_more' : 'expand_less'}
              </span>
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={onClose}
            title="Close"
          >
            <span className="material-icons-outlined text-lg">close</span>
          </Button>
        </div>

        {/* Content container */}
        <div className="h-full flex flex-col">
          {/* Collapsed view - Mini Bar */}
          {!isExpanded && (
            <div className="flex-1 flex flex-col">
              {/* Main row with preview and controls */}
              <div className="flex-1 flex items-center gap-6 px-6">
                {/* Current Pattern Preview - Rounded (click to expand) */}
                <div
                  className="w-48 h-48 rounded-full overflow-hidden bg-muted shrink-0 border-2 cursor-pointer hover:border-primary transition-colors"
                  onClick={() => isPlaying && setIsExpanded(true)}
                  title={isPlaying ? 'Click to expand' : undefined}
                >
                  {previewUrl && isPlaying ? (
                    <img
                      src={previewUrl}
                      alt={patternName}
                      className="w-full h-full object-cover pattern-preview"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      <span className="material-icons-outlined text-muted-foreground text-4xl">
                        {isPlaying ? 'image' : 'hourglass_empty'}
                      </span>
                    </div>
                  )}
                </div>

                {/* Main Content Area */}
                {isPlaying && status ? (
                  <>
                    <div className="flex-1 min-w-0 flex flex-col justify-center gap-2 py-2">
                      {/* Title Row */}
                      <div className="flex items-center gap-3 pr-12 md:pr-16">
                        <div className="flex-1 min-w-0">
                          <div className="marquee-container">
                            <p className="text-sm md:text-base font-semibold whitespace-nowrap animate-marquee">
                              {patternName}
                            </p>
                          </div>
                          {status.playlist && (
                            <p className="text-xs text-muted-foreground">
                              Pattern {status.playlist.current_index + 1} of {status.playlist.total_files}
                            </p>
                          )}
                        </div>
                      </div>

                      {/* Progress Bar - Desktop only (inline, above controls) */}
                      <div className="hidden md:flex items-center gap-3">
                        <span className="text-sm text-muted-foreground w-12 font-mono">{formatTime(elapsedTime)}</span>
                        <Progress value={progressPercent} className="h-2 flex-1" />
                        <span className="text-sm text-muted-foreground w-12 text-right font-mono">-{formatTime(remainingTime)}</span>
                      </div>

                      {/* Playback Controls - Centered */}
                      <div className="flex items-center justify-center gap-3">
                        <Button
                          variant="outline"
                          size="icon"
                          className="h-10 w-10 rounded-full"
                          onClick={handleStop}
                          title="Stop"
                        >
                          <span className="material-icons">stop</span>
                        </Button>
                        <Button
                          variant="default"
                          size="icon"
                          className="h-12 w-12 rounded-full"
                          onClick={handlePause}
                        >
                          <span className="material-icons text-xl">
                            {status.is_paused ? 'play_arrow' : 'pause'}
                          </span>
                        </Button>
                        {status.playlist && (
                          <Button
                            variant="outline"
                            size="icon"
                            className="h-10 w-10 rounded-full"
                            onClick={handleSkip}
                            title="Skip to next"
                          >
                            <span className="material-icons">skip_next</span>
                          </Button>
                        )}
                      </div>

                      {/* Speed Control */}
                      <div className="flex items-center justify-center gap-2">
                        <span className="text-sm text-muted-foreground">Speed:</span>
                        <Input
                          type="number"
                          placeholder={String(status.speed)}
                          value={speedInput}
                          onChange={(e) => setSpeedInput(e.target.value)}
                          onKeyDown={(e) => e.key === 'Enter' && handleSpeedSubmit()}
                          className="h-7 w-20 text-sm px-2"
                        />
                        <span className="text-sm text-muted-foreground">mm/s</span>
                      </div>
                    </div>

                    {/* Next Pattern Preview - hidden on mobile */}
                    {status.playlist?.next_file && (
                      <div className="hidden md:flex shrink-0 flex-col items-center gap-1 mr-16">
                        <p className="text-xs text-muted-foreground font-medium">Up Next</p>
                        <div className="w-24 h-24 rounded-full overflow-hidden bg-muted border-2">
                          {nextPreviewUrl ? (
                            <img
                              src={nextPreviewUrl}
                              alt="Next pattern"
                              className="w-full h-full object-cover pattern-preview"
                            />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center">
                              <span className="material-icons-outlined text-muted-foreground text-2xl">image</span>
                            </div>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground text-center max-w-24 truncate">
                          {formatPatternName(status.playlist.next_file)}
                        </p>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="flex-1 flex items-center">
                    <p className="text-lg text-muted-foreground">Not playing</p>
                  </div>
                )}
              </div>

              {/* Progress Bar - Mobile only (full width at bottom) */}
              {isPlaying && status && (
                <div className="flex md:hidden items-center gap-3 px-6 pb-3">
                  <span className="text-sm text-muted-foreground w-12 font-mono">{formatTime(elapsedTime)}</span>
                  <Progress value={progressPercent} className="h-2 flex-1" />
                  <span className="text-sm text-muted-foreground w-12 text-right font-mono">-{formatTime(remainingTime)}</span>
                </div>
              )}
            </div>
          )}

          {/* Expanded view - Real-time canvas preview */}
          {isExpanded && isPlaying && (
            <div className="flex-1 flex flex-col md:items-center md:justify-center px-4 py-2 md:py-4 overflow-hidden">
              <div className="w-full max-w-5xl mx-auto flex flex-col md:flex-row md:items-center md:justify-center gap-3 md:gap-6">
                {/* Canvas - full width on mobile (click to collapse) */}
                <div
                  className="flex items-center justify-center flex-1 md:flex-none min-h-0 cursor-pointer"
                  onClick={() => setIsExpanded(false)}
                  title="Click to collapse"
                >
                  <canvas
                    ref={canvasRef}
                    width={600}
                    height={600}
                    className="w-full max-h-full rounded-full border-2 md:w-auto hover:border-primary transition-colors"
                    style={{ aspectRatio: '1/1', maxHeight: '40vh' }}
                  />
                </div>

                {/* Controls */}
                <div className="md:w-80 shrink-0 flex flex-col justify-start md:justify-center gap-2 md:gap-4">
                {/* Pattern Info */}
                <div className="text-center">
                  <h2 className="text-lg md:text-xl font-semibold truncate">{patternName}</h2>
                  {status?.playlist && (
                    <p className="text-sm text-muted-foreground">
                      Pattern {status.playlist.current_index + 1} of {status.playlist.total_files}
                    </p>
                  )}
                </div>

                {/* Progress */}
                <div className="space-y-1 md:space-y-2">
                  <Progress value={progressPercent} className="h-1.5 md:h-2" />
                  <div className="flex justify-between text-xs md:text-sm text-muted-foreground font-mono">
                    <span>{formatTime(elapsedTime)}</span>
                    <span>{progressPercent.toFixed(0)}%</span>
                    <span>-{formatTime(remainingTime)}</span>
                  </div>
                </div>

                {/* Playback Controls */}
                <div className="flex items-center justify-center gap-2 md:gap-3">
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-10 w-10 md:h-12 md:w-12 rounded-full"
                    onClick={handleStop}
                    title="Stop"
                  >
                    <span className="material-icons text-lg md:text-2xl">stop</span>
                  </Button>
                  <Button
                    variant="default"
                    size="icon"
                    className="h-12 w-12 md:h-14 md:w-14 rounded-full"
                    onClick={handlePause}
                  >
                    <span className="material-icons text-xl md:text-2xl">
                      {status?.is_paused ? 'play_arrow' : 'pause'}
                    </span>
                  </Button>
                  {status?.playlist && (
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-10 w-10 md:h-12 md:w-12 rounded-full"
                      onClick={handleSkip}
                      title="Skip to next"
                    >
                      <span className="material-icons text-lg md:text-2xl">skip_next</span>
                    </Button>
                  )}
                </div>

                {/* Speed Control */}
                <div className="flex items-center justify-center gap-2">
                  <span className="text-sm text-muted-foreground">Speed:</span>
                  <Input
                    type="number"
                    placeholder={String(status?.speed || 1000)}
                    value={speedInput}
                    onChange={(e) => setSpeedInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSpeedSubmit()}
                    className="h-8 w-24 text-sm px-2"
                  />
                  <span className="text-sm text-muted-foreground">mm/s</span>
                </div>

                {/* Next Pattern */}
                {status?.playlist?.next_file && (
                  <div className="flex items-center gap-3 bg-muted/50 rounded-lg p-2 md:p-3">
                    <div className="w-10 h-10 md:w-12 md:h-12 rounded-full overflow-hidden bg-muted border shrink-0">
                      {nextPreviewUrl ? (
                        <img
                          src={nextPreviewUrl}
                          alt="Next pattern"
                          className="w-full h-full object-cover pattern-preview"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center">
                          <span className="material-icons-outlined text-muted-foreground text-sm">image</span>
                        </div>
                      )}
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-muted-foreground">Up Next</p>
                      <p className="text-sm font-medium truncate">
                        {formatPatternName(status.playlist.next_file)}
                      </p>
                    </div>
                  </div>
                )}
              </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
