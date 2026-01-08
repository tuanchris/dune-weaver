import { useState, useEffect, useRef } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'

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
  onClose: () => void
}

export function NowPlayingBar({ isLogsOpen = false, isVisible, onClose }: NowPlayingBarProps) {
  const [status, setStatus] = useState<PlaybackStatus | null>(null)
  const [isExpanded, setIsExpanded] = useState(false)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  // Connect to status WebSocket
  useEffect(() => {
    const connectWebSocket = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws/status`)

      ws.onmessage = (event) => {
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

  // Fetch preview image when current file changes
  useEffect(() => {
    const currentFile = status?.current_file
    if (currentFile) {
      fetch('/preview_thr_batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_names: [currentFile] }),
      })
        .then((r) => r.json())
        .then((data) => {
          if (data[currentFile]?.image_data) {
            setPreviewUrl(data[currentFile].image_data)
          }
        })
        .catch(() => {})
    } else {
      setPreviewUrl(null)
    }
  }, [status?.current_file])

  const handlePause = async () => {
    try {
      const endpoint = status?.is_paused ? '/resume_execution' : '/pause_execution'
      const response = await fetch(endpoint, { method: 'POST' })
      if (!response.ok) throw new Error()
      toast.success(status?.is_paused ? 'Resumed' : 'Paused')
    } catch {
      toast.error('Failed to toggle pause')
    }
  }

  const handleStop = async () => {
    try {
      const response = await fetch('/stop_execution', { method: 'POST' })
      if (!response.ok) throw new Error()
      toast.success('Stopped')
    } catch {
      toast.error('Failed to stop')
    }
  }

  const handleSkip = async () => {
    try {
      const response = await fetch('/skip_pattern', { method: 'POST' })
      if (!response.ok) throw new Error()
      toast.success('Skipping to next pattern')
    } catch {
      toast.error('Failed to skip')
    }
  }

  // Don't render if not visible
  if (!isVisible) {
    return null
  }

  const isPlaying = status?.is_running || status?.is_paused
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

      {/* Now Playing Bar */}
      <div
        className={`fixed left-0 right-0 z-40 bg-background border-t shadow-lg transition-all duration-300 ${
          isExpanded ? 'rounded-t-xl' : ''
        } ${isLogsOpen ? 'bottom-80' : 'bottom-16'}`}
      >
        {/* Mini Bar (always visible) */}
        <div
          className="flex items-center gap-3 px-4 py-2 cursor-pointer"
          onClick={() => isPlaying && setIsExpanded(!isExpanded)}
        >
          {/* Pattern Preview */}
          <div className="w-10 h-10 rounded-full overflow-hidden bg-muted shrink-0 border">
            {previewUrl && isPlaying ? (
              <img
                src={previewUrl}
                alt={patternName}
                className="w-full h-full object-cover pattern-preview"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center">
                <span className="material-icons-outlined text-muted-foreground text-lg">
                  {isPlaying ? 'image' : 'hourglass_empty'}
                </span>
              </div>
            )}
          </div>

          {/* Pattern Info */}
          <div className="flex-1 min-w-0">
            {isPlaying ? (
              <>
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium truncate">{patternName}</p>
                  {status?.is_paused && (
                    <span className="text-xs text-muted-foreground">(Paused)</span>
                  )}
                </div>
                <Progress value={progressPercent} className="h-1 mt-1" />
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Not playing</p>
            )}
          </div>

          {/* Quick Controls */}
          {isPlaying && (
            <div className="flex items-center gap-1 shrink-0">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={(e) => {
                  e.stopPropagation()
                  handlePause()
                }}
              >
                <span className="material-icons text-lg">
                  {status?.is_paused ? 'play_arrow' : 'pause'}
                </span>
              </Button>
              {status?.playlist && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={(e) => {
                    e.stopPropagation()
                    handleSkip()
                  }}
                >
                  <span className="material-icons text-lg">skip_next</span>
                </Button>
              )}
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={(e) => {
                  e.stopPropagation()
                  handleStop()
                }}
              >
                <span className="material-icons text-lg">stop</span>
              </Button>
            </div>
          )}

          {/* Expand/Close Indicator */}
          {isPlaying ? (
            <span
              className={`material-icons-outlined text-muted-foreground transition-transform ${
                isExpanded ? 'rotate-180' : ''
              }`}
            >
              expand_less
            </span>
          ) : (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={(e) => {
                e.stopPropagation()
                onClose()
              }}
            >
              <span className="material-icons-outlined text-lg">close</span>
            </Button>
          )}
        </div>

        {/* Expanded View */}
        {isExpanded && isPlaying && (
          <div className="px-4 pb-4 pt-2 border-t space-y-4">
            {/* Time Info */}
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">
                {formatTime(elapsedTime)}
              </span>
              <span className="text-muted-foreground">
                -{formatTime(remainingTime)}
              </span>
            </div>

            {/* Progress Bar */}
            <Progress value={progressPercent} className="h-2" />

            {/* Playback Controls */}
            <div className="flex items-center justify-center gap-4">
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
              <Button
                variant="outline"
                size="icon"
                className="h-10 w-10 rounded-full"
                onClick={handleStop}
                title="Stop"
              >
                <span className="material-icons">stop</span>
              </Button>
            </div>

            {/* Details Grid */}
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="bg-muted/50 rounded-lg p-3">
                <p className="text-muted-foreground text-xs">Speed</p>
                <p className="font-medium">{status.speed} mm/s</p>
              </div>
              <div className="bg-muted/50 rounded-lg p-3">
                <p className="text-muted-foreground text-xs">Progress</p>
                <p className="font-medium">{progressPercent.toFixed(0)}%</p>
              </div>
              {status.playlist && (
                <>
                  <div className="bg-muted/50 rounded-lg p-3">
                    <p className="text-muted-foreground text-xs">Playlist</p>
                    <p className="font-medium">
                      {status.playlist.current_index + 1} of {status.playlist.total_files}
                    </p>
                  </div>
                  <div className="bg-muted/50 rounded-lg p-3">
                    <p className="text-muted-foreground text-xs">Next</p>
                    <p className="font-medium truncate">
                      {status.playlist.next_file
                        ? formatPatternName(status.playlist.next_file)
                        : 'None'}
                    </p>
                  </div>
                </>
              )}
            </div>

            {/* Pause Time Remaining (if in pause between patterns) */}
            {status.pause_time_remaining > 0 && (
              <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-3 text-center">
                <p className="text-sm text-amber-600 dark:text-amber-400">
                  <span className="material-icons-outlined text-base align-middle mr-1">
                    schedule
                  </span>
                  Next pattern in {formatTime(status.pause_time_remaining)}
                </p>
              </div>
            )}

            {/* Scheduled Pause Indicator */}
            {status.scheduled_pause && (
              <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-3 text-center">
                <p className="text-sm text-blue-600 dark:text-blue-400">
                  <span className="material-icons-outlined text-base align-middle mr-1">
                    bedtime
                  </span>
                  Scheduled pause active
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  )
}
