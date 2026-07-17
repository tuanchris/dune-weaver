import { useState, useEffect, useRef } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { apiClient } from '@/lib/apiClient'
import { useStatusStore } from '@/stores/useStatusStore'

// Reset causes that mean the board crashed (vs. a clean power/software reset).
const CRASH_RESETS = ['panic', 'int_wdt', 'task_wdt', 'wdt', 'brownout']

const formatKB = (n: number | null | undefined): string =>
  n === null || n === undefined ? '—' : `${Math.round(n / 1024)} KB`

const formatUptime = (s: number | null | undefined): string => {
  if (s === null || s === undefined) return '—'
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

// Human-readable label for a last_reset cause.
const RESET_LABELS: Record<string, string> = {
  power_on: 'Power on',
  software: 'Software',
  panic: 'Panic (crash)',
  int_wdt: 'Interrupt watchdog',
  task_wdt: 'Task watchdog',
  wdt: 'Watchdog',
  brownout: 'Brownout',
  external: 'External',
  deepsleep: 'Deep sleep',
  unknown: 'Unknown',
}

export function TableControlPage() {
  const [speedInput, setSpeedInput] = useState('')
  const [currentSpeed, setCurrentSpeed] = useState<number | null>(null)
  const [currentTheta, setCurrentTheta] = useState(0)
  const [isLoading, setIsLoading] = useState<string | null>(null)

  // Subscribe to shared status WebSocket via store
  const speed = useStatusStore((s) => s.status?.speed ?? null)
  const isPatternRunning = useStatusStore((s) =>
    (s.status?.is_running || s.status?.is_paused) ?? false
  )
  // Board health telemetry (heap/last_reset/sd_ok) rides the /ws/status payload.
  const health = useStatusStore((s) => s.status?.health ?? null)

  // Sync speed from store into local state (for the badge display)
  useEffect(() => {
    if (speed !== null) setCurrentSpeed(speed)
  }, [speed])

  // Command console state
  const [consoleCommand, setConsoleCommand] = useState('')
  const [consoleHistory, setConsoleHistory] = useState<Array<{ type: 'cmd' | 'resp' | 'error'; text: string; time: string }>>([])

  // Table Log and Boot Log now live in the shared "View Logs" drawer (Layout),
  // so they can sit next to the application logs. See Layout.tsx.

  const [consoleLoading, setConsoleLoading] = useState(false)
  const consoleOutputRef = useRef<HTMLDivElement>(null)
  const consoleInputRef = useRef<HTMLInputElement>(null)

  const handleAction = async (
    action: string,
    endpoint: string,
    body?: object
  ) => {
    setIsLoading(action)
    try {
      const data = await apiClient.post<{ success?: boolean; detail?: string }>(endpoint, body)
      if (data.success !== false) {
        return { success: true, data }
      }
      throw new Error(data.detail || 'Action failed')
    } catch (error) {
      console.error(`Error with ${action}:`, error)
      throw error
    } finally {
      setIsLoading(null)
    }
  }

  // Helper to check if pattern is running and show warning
  const checkPatternRunning = (actionName: string): boolean => {
    if (isPatternRunning) {
      toast.error(`Cannot ${actionName} while a pattern is running. Stop the pattern first.`, {
        action: {
          label: 'Stop',
          onClick: () => handleStop(),
        },
      })
      return true
    }
    return false
  }

  const handleHome = async () => {
    try {
      await handleAction('home', '/send_home')
      toast.success('Moving to home position...')
    } catch {
      toast.error('Failed to move to home position')
    }
  }

  const handleStop = async () => {
    try {
      await handleAction('stop', '/stop_execution')
      toast.success('Execution stopped')
    } catch {
      // Normal stop failed, try force stop
      try {
        await handleAction('stop', '/force_stop')
        toast.success('Force stopped')
      } catch {
        toast.error('Failed to stop execution')
      }
    }
  }

  const handleReset = async () => {
    try {
      await handleAction('reset', '/soft_reset')
      toast.success('Reset sent. Please home the table.')
    } catch {
      toast.error('Failed to send reset command')
    }
  }

  const handleMoveToCenter = async () => {
    if (checkPatternRunning('move to center')) return
    try {
      await handleAction('center', '/move_to_center')
      toast.success('Moving to center...')
    } catch {
      toast.error('Failed to move to center')
    }
  }

  const handleMoveToPerimeter = async () => {
    if (checkPatternRunning('move to perimeter')) return
    try {
      await handleAction('perimeter', '/move_to_perimeter')
      toast.success('Moving to perimeter...')
    } catch {
      toast.error('Failed to move to perimeter')
    }
  }

  const handleSetSpeed = async () => {
    const speed = parseFloat(speedInput)
    if (isNaN(speed) || speed <= 0) {
      toast.error('Please enter a valid speed value')
      return
    }
    try {
      await handleAction('speed', '/set_speed', { speed })
      setCurrentSpeed(speed)
      toast.success(`Speed set to ${speed} mm/s`)
      setSpeedInput('')
    } catch {
      toast.error('Failed to set speed')
    }
  }

  const handleClearPattern = async (patternFile: string, label: string) => {
    try {
      await handleAction(patternFile, '/run_theta_rho', {
        file_name: patternFile,
        pre_execution: 'none',
      })
      toast.success(`Running ${label}...`)
    } catch (error) {
      if (error instanceof Error && error.message.includes('409')) {
        toast.error('Another pattern is already running')
      } else {
        toast.error(`Failed to run ${label}`)
      }
    }
  }

  const handleRotate = async (degrees: number) => {
    if (checkPatternRunning('align')) return
    try {
      const radians = degrees * (Math.PI / 180)
      const newTheta = currentTheta + radians
      await handleAction('rotate', '/send_coordinate', { theta: newTheta, rho: 1 })
      setCurrentTheta(newTheta)
      toast.info(`Rotated ${degrees}°`)
    } catch {
      toast.error('Failed to rotate')
    }
  }

  // Board command console: sends $-commands to the FluidNC firmware through
  // the backend (/api/board/command); output comes from the board's reply and
  // its rolling session log.
  const addConsoleHistory = (type: 'cmd' | 'resp' | 'error', text: string) => {
    const time = new Date().toLocaleTimeString()
    setConsoleHistory((prev) => [...prev.slice(-200), { type, text, time }])
    setTimeout(() => {
      if (consoleOutputRef.current) {
        consoleOutputRef.current.scrollTop = consoleOutputRef.current.scrollHeight
      }
    }, 10)
  }

  const handleConsoleSend = async () => {
    if (!consoleCommand.trim() || consoleLoading) return

    const cmd = consoleCommand.trim()
    setConsoleCommand('')
    setConsoleLoading(true)
    addConsoleHistory('cmd', cmd)

    try {
      const data = await apiClient.post<{ responses?: string[]; log?: string; detail?: string }>(
        '/api/board/command', { command: cmd })
      const lines = data.responses ?? []
      if (lines.length > 0) {
        lines.forEach((line: string) => addConsoleHistory('resp', line))
      } else if (data.log) {
        data.log.split('\n').slice(-5).forEach((line: string) => addConsoleHistory('resp', line))
      } else {
        addConsoleHistory('resp', '(no response — check the board log)')
      }
    } catch (error) {
      addConsoleHistory('error', `Error: ${error}`)
    } finally {
      setConsoleLoading(false)
      setTimeout(() => consoleInputRef.current?.focus(), 0)
    }
  }

  const handleConsoleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (!consoleLoading) {
        handleConsoleSend()
      }
    }
  }

  return (
    <TooltipProvider>
      <div className="flex flex-col w-full max-w-5xl mx-auto gap-6 py-3 sm:py-6 px-0 sm:px-4">
        {/* Page Header */}
        <div className="space-y-0.5 sm:space-y-1 pl-1">
          <h1 className="text-xl font-semibold tracking-tight font-display">Table Control</h1>
          <p className="text-xs text-muted-foreground">
            Manual controls for your sand table
          </p>
        </div>

        <Separator />

        {/* Main Controls Grid - 2x2 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Primary Actions */}
          <Card className="transition-all duration-200 hover:shadow-md hover:border-primary/20">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg">Primary Actions</CardTitle>
              <CardDescription>Calibrate or stop the table</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-3">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      onClick={handleHome}
                      disabled={isLoading === 'home'}
                      variant="primary"
                      className="h-16 gap-1 flex-col items-center justify-center"
                    >
                      {isLoading === 'home' ? (
                        <span className="material-icons-outlined animate-spin text-2xl">sync</span>
                      ) : (
                        <span className="material-icons-outlined text-2xl">home</span>
                      )}
                      <span className="text-xs">Home</span>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Return to home position</TooltipContent>
                </Tooltip>

                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      onClick={handleStop}
                      disabled={isLoading === 'stop'}
                      variant="destructive"
                      className="h-16 gap-1 flex-col items-center justify-center"
                    >
                      {isLoading === 'stop' ? (
                        <span className="material-icons-outlined animate-spin text-2xl">sync</span>
                      ) : (
                        <span className="material-icons-outlined text-2xl">stop_circle</span>
                      )}
                      <span className="text-xs">Stop</span>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Gracefully stop</TooltipContent>
                </Tooltip>

                <Dialog>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <DialogTrigger asChild>
                        <Button
                          disabled={isLoading === 'reset'}
                          variant="secondary"
                          className="h-16 gap-1 flex-col items-center justify-center"
                        >
                          {isLoading === 'reset' ? (
                            <span className="material-icons-outlined animate-spin text-2xl">sync</span>
                          ) : (
                            <span className="material-icons-outlined text-2xl">restart_alt</span>
                          )}
                          <span className="text-xs">Reset</span>
                        </Button>
                      </DialogTrigger>
                    </TooltipTrigger>
                    <TooltipContent>Send soft reset to controller</TooltipContent>
                  </Tooltip>
                  <DialogContent className="sm:max-w-md">
                    <DialogHeader>
                      <DialogTitle>Reset Controller?</DialogTitle>
                      <DialogDescription>
                        This will send a soft reset to the controller.
                      </DialogDescription>
                    </DialogHeader>
                    <Alert className="flex items-center border-primary/40">
                      <span className="material-icons-outlined text-primary text-base mr-2 shrink-0">warning</span>
                      <AlertDescription className="text-primary">
                        Homing is required after resetting. The table will lose its position reference.
                      </AlertDescription>
                    </Alert>
                    <DialogFooter className="gap-2 sm:gap-0">
                      <DialogTrigger asChild>
                        <Button variant="outline">Cancel</Button>
                      </DialogTrigger>
                      <DialogTrigger asChild>
                        <Button variant="destructive" onClick={handleReset}>
                          Reset Controller
                        </Button>
                      </DialogTrigger>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
              </div>
            </CardContent>
          </Card>

          {/* Speed Control */}
          <Card className="transition-all duration-200 hover:shadow-md hover:border-primary/20">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-lg">Speed</CardTitle>
                  <CardDescription>Ball movement speed</CardDescription>
                </div>
                <Badge variant="secondary" className="font-mono">
                  {currentSpeed !== null ? `${currentSpeed} mm/s` : '-- mm/s'}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex gap-2">
                <Input
                  type="number"
                  value={speedInput}
                  onChange={(e) => setSpeedInput(e.target.value)}
                  placeholder="mm/s"
                  min="1"
                  step="1"
                  className="flex-1"
                  onKeyDown={(e) => e.key === 'Enter' && handleSetSpeed()}
                />
                <Button
                  onClick={handleSetSpeed}
                  disabled={isLoading === 'speed' || !speedInput}
                  className="gap-2"
                >
                  {isLoading === 'speed' ? (
                    <span className="material-icons-outlined animate-spin">sync</span>
                  ) : (
                    <span className="material-icons-outlined">check</span>
                  )}
                  Set
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Position */}
          <Card className="transition-all duration-200 hover:shadow-md hover:border-primary/20">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg">Position</CardTitle>
              <CardDescription>Move ball to a specific location</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-3">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      onClick={handleMoveToCenter}
                      disabled={isLoading === 'center'}
                      variant="secondary"
                      className="h-16 gap-1 flex-col items-center justify-center"
                    >
                      {isLoading === 'center' ? (
                        <span className="material-icons-outlined animate-spin text-2xl">sync</span>
                      ) : (
                        <span className="material-icons-outlined text-2xl">center_focus_strong</span>
                      )}
                      <span className="text-xs">Center</span>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Move ball to center</TooltipContent>
                </Tooltip>

                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      onClick={handleMoveToPerimeter}
                      disabled={isLoading === 'perimeter'}
                      variant="secondary"
                      className="h-16 gap-1 flex-col items-center justify-center"
                    >
                      {isLoading === 'perimeter' ? (
                        <span className="material-icons-outlined animate-spin text-2xl">sync</span>
                      ) : (
                        <span className="material-icons-outlined text-2xl">trip_origin</span>
                      )}
                      <span className="text-xs">Perimeter</span>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Move ball to edge</TooltipContent>
                </Tooltip>

                <Dialog>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <DialogTrigger asChild>
                        <Button
                          variant="secondary"
                          className="h-16 gap-1 flex-col items-center justify-center"
                        >
                          <span className="material-icons-outlined text-2xl">screen_rotation</span>
                          <span className="text-xs">Align</span>
                        </Button>
                      </DialogTrigger>
                    </TooltipTrigger>
                    <TooltipContent>Align pattern orientation</TooltipContent>
                  </Tooltip>
                <DialogContent className="sm:max-w-md">
                  <DialogHeader>
                    <DialogTitle>Pattern Orientation Alignment</DialogTitle>
                    <DialogDescription>
                      Follow these steps to align your patterns with their previews
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-4 py-4">
                    <ol className="space-y-3 text-sm">
                      {[
                        'Home the table then select move to perimeter. Look at your pattern preview and decide where the "bottom" should be.',
                        'Manually move the radial arm or use the rotation buttons below to point 90° to the right of where you want the pattern bottom.',
                        'Click the "Home" button to establish this as the reference position.',
                        'All patterns will now be oriented according to their previews!',
                      ].map((step, i) => (
                        <li key={i} className="flex gap-3">
                          <Badge
                            variant="secondary"
                            className="h-6 w-6 shrink-0 items-center justify-center rounded-full p-0"
                          >
                            {i + 1}
                          </Badge>
                          <span className="text-muted-foreground">{step}</span>
                        </li>
                      ))}
                    </ol>

                    <Separator />

                    <Alert className="flex items-start border-primary/40">
                      <span className="material-icons-outlined text-primary text-base mr-2 shrink-0">
                        warning
                      </span>
                      <AlertDescription className="text-primary">
                        Only perform this when you want to change the orientation reference.
                      </AlertDescription>
                    </Alert>

                    <div className="space-y-3">
                      <p className="text-sm font-medium text-center">Fine Adjustment</p>
                      <div className="flex justify-center gap-2">
                        <Button
                          variant="secondary"
                          onClick={() => handleRotate(-10)}
                          disabled={isLoading === 'rotate'}
                        >
                          <span className="material-icons text-lg mr-1">rotate_left</span>
                          CCW 10°
                        </Button>
                        <Button
                          variant="secondary"
                          onClick={() => handleRotate(10)}
                          disabled={isLoading === 'rotate'}
                        >
                          CW 10°
                          <span className="material-icons text-lg ml-1">rotate_right</span>
                        </Button>
                      </div>
                      <p className="text-xs text-muted-foreground text-center">
                        Each click rotates 10 degrees
                      </p>
                    </div>
                  </div>
                  <DialogFooter>
                    <DialogTrigger asChild>
                      <Button>Got it</Button>
                    </DialogTrigger>
                  </DialogFooter>
                </DialogContent>
                </Dialog>
              </div>
            </CardContent>
          </Card>

          {/* Clear Patterns */}
          <Card className="transition-all duration-200 hover:shadow-md hover:border-primary/20">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg">Clear Sand</CardTitle>
              <CardDescription>Erase current pattern from the table</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-3">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      onClick={() => handleClearPattern('clear_from_in.thr', 'clear from center')}
                      disabled={isLoading === 'clear_from_in.thr'}
                      variant="secondary"
                      className="h-16 gap-1 flex-col items-center justify-center"
                    >
                      {isLoading === 'clear_from_in.thr' ? (
                        <span className="material-icons-outlined animate-spin text-2xl">sync</span>
                      ) : (
                        <span className="material-icons-outlined text-2xl">center_focus_strong</span>
                      )}
                      <span className="text-xs">Clear Center</span>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Spiral outward from center</TooltipContent>
                </Tooltip>

                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      onClick={() => handleClearPattern('clear_from_out.thr', 'clear from perimeter')}
                      disabled={isLoading === 'clear_from_out.thr'}
                      variant="secondary"
                      className="h-16 gap-1 flex-col items-center justify-center"
                    >
                      {isLoading === 'clear_from_out.thr' ? (
                        <span className="material-icons-outlined animate-spin text-2xl">sync</span>
                      ) : (
                        <span className="material-icons-outlined text-2xl">all_out</span>
                      )}
                      <span className="text-xs">Clear Edge</span>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Spiral inward from edge</TooltipContent>
                </Tooltip>

                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      onClick={() => handleClearPattern('clear_sideway.thr', 'clear sideways')}
                      disabled={isLoading === 'clear_sideway.thr'}
                      variant="secondary"
                      className="h-16 gap-1 flex-col items-center justify-center"
                    >
                      {isLoading === 'clear_sideway.thr' ? (
                        <span className="material-icons-outlined animate-spin text-2xl">sync</span>
                      ) : (
                        <span className="material-icons-outlined text-2xl">swap_horiz</span>
                      )}
                      <span className="text-xs">Clear Sideways</span>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Clear with side-to-side motion</TooltipContent>
                </Tooltip>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Board Diagnostics — health telemetry + on-device crash breadcrumbs */}
        <Card className="transition-all duration-200 hover:shadow-md hover:border-primary/20">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg flex items-center gap-2">
              <span className="material-icons-outlined text-xl">monitor_heart</span>
              Diagnostics
            </CardTitle>
            <CardDescription>
              Board health and crash breadcrumbs reported by the firmware.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!health ? (
              <p className="text-sm text-muted-foreground">
                No telemetry yet — connect to a table running firmware that reports health.
              </p>
            ) : (
              <>
                {/* Crash / SD / fragmentation banners */}
                {health.last_reset && CRASH_RESETS.includes(health.last_reset) && (
                  <Alert variant="destructive">
                    <AlertDescription>
                      The table last rebooted from a{' '}
                      <strong>{RESET_LABELS[health.last_reset] ?? health.last_reset}</strong>.
                      Open the menu → View Logs → Boot Log for the cause.
                    </AlertDescription>
                  </Alert>
                )}
                {health.sd_ok === false && (
                  <Alert className="border-primary/40 text-primary">
                    <AlertDescription>
                      SD card unreadable at boot — patterns and playlists may be unavailable.
                      Re-seat the card and reboot the table.
                    </AlertDescription>
                  </Alert>
                )}
                {health.heap_largest !== null && health.heap_largest !== undefined &&
                  health.heap_largest < 12000 && (
                  <Alert className="border-primary/40 text-primary">
                    <AlertDescription>
                      Low memory: largest free block is {formatKB(health.heap_largest)}. Heap
                      fragmentation is trending toward an out-of-memory reboot.
                    </AlertDescription>
                  </Alert>
                )}

                {/* Stat grid */}
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  <div className="space-y-1">
                    <div className="text-xs text-muted-foreground">Last reset</div>
                    <Badge variant={health.last_reset && CRASH_RESETS.includes(health.last_reset)
                      ? 'destructive' : 'secondary'}>
                      {health.last_reset
                        ? (RESET_LABELS[health.last_reset] ?? health.last_reset)
                        : '—'}
                    </Badge>
                  </div>
                  <div className="space-y-1">
                    <div className="text-xs text-muted-foreground">SD card</div>
                    <Badge variant={health.sd_ok === false ? 'destructive' : 'secondary'}>
                      {health.sd_ok === true ? 'OK' : health.sd_ok === false ? 'Error' : '—'}
                    </Badge>
                  </div>
                  <div className="space-y-1">
                    <div className="text-xs text-muted-foreground">Uptime</div>
                    <div className="text-sm font-medium font-mono">{formatUptime(health.uptime)}</div>
                  </div>
                  <div className="space-y-1">
                    <div className="text-xs text-muted-foreground">Free heap</div>
                    <div className="text-sm font-medium font-mono">{formatKB(health.heap)}</div>
                  </div>
                  <div className="space-y-1">
                    <div className="text-xs text-muted-foreground">Min heap</div>
                    <div className="text-sm font-medium font-mono">{formatKB(health.heap_min)}</div>
                  </div>
                  <div className="space-y-1">
                    <div className="text-xs text-muted-foreground">Largest block</div>
                    <div className="text-sm font-medium font-mono">{formatKB(health.heap_largest)}</div>
                  </div>
                </div>
              </>
            )}

            <p className="text-xs text-muted-foreground pt-1">
              The boot log and the table's full history live in the menu → View Logs drawer.
            </p>
          </CardContent>
        </Card>

        {/* Board Command Console */}
        <Card className="transition-all duration-200 hover:shadow-md hover:border-primary/20">
          <CardHeader className="pb-3 space-y-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 space-y-2">
                <CardTitle className="text-lg flex items-center gap-2">
                  <span className="material-icons-outlined text-xl">terminal</span>
                  Command Console
                </CardTitle>
                <CardDescription className="hidden sm:block">
                  Send $-commands to the table's firmware (e.g. $Sand/HomingMode, $LED/Effect=fire)
                </CardDescription>
                <Alert className="flex items-center border-primary/40 py-2">
                  <span className="material-icons-outlined text-primary text-base mr-2 shrink-0">warning</span>
                  <AlertDescription className="text-xs text-primary">
                    For advanced use. Motion commands sent here can interfere with a running pattern.
                  </AlertDescription>
                </Alert>
              </div>
              {consoleHistory.length > 0 && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setConsoleHistory([])}
                  title="Clear history"
                >
                  <span className="material-icons-outlined">delete_sweep</span>
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {/* Output area */}
            <div
              ref={consoleOutputRef}
              className="bg-black/90 rounded-md p-3 h-48 overflow-y-auto font-mono text-sm mb-3"
            >
              {consoleHistory.length > 0 ? (
                consoleHistory.map((entry, i) => (
                  <div
                    key={i}
                    className={`${
                      entry.type === 'cmd'
                        ? 'text-live'
                        : entry.type === 'error'
                          ? 'text-destructive'
                          : 'text-success'
                    }`}
                  >
                    <span className="text-muted-foreground text-xs mr-2">{entry.time}</span>
                    {entry.type === 'cmd' ? '> ' : ''}
                    {entry.text}
                  </div>
                ))
              ) : (
                <div className="text-muted-foreground italic">
                  Ready. Enter a firmware command (e.g. $Sand/HomingMode, $Playlist/List)
                </div>
              )}
            </div>

            {/* Input area */}
            <div className="flex gap-2">
              <Input
                ref={consoleInputRef}
                value={consoleCommand}
                onChange={(e) => setConsoleCommand(e.target.value)}
                onKeyDown={handleConsoleKeyDown}
                readOnly={consoleLoading}
                placeholder="Enter command (e.g. $Sand/HomingMode)"
                className="font-mono text-base h-11"
              />
              <Button
                onClick={handleConsoleSend}
                disabled={!consoleCommand.trim() || consoleLoading}
                className="h-11 px-6"
              >
                {consoleLoading ? (
                  <span className="material-icons-outlined animate-spin">sync</span>
                ) : (
                  <span className="material-icons-outlined">send</span>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </TooltipProvider>
  )
}
