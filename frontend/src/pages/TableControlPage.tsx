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

export function TableControlPage() {
  const [speedInput, setSpeedInput] = useState('')
  const [currentSpeed, setCurrentSpeed] = useState<number | null>(null)
  const [currentTheta, setCurrentTheta] = useState(0)
  const [isLoading, setIsLoading] = useState<string | null>(null)
  const [isPatternRunning, setIsPatternRunning] = useState(false)

  // Serial terminal state
  const [serialPorts, setSerialPorts] = useState<string[]>([])
  const [selectedSerialPort, setSelectedSerialPort] = useState('')
  const [serialConnected, setSerialConnected] = useState(false)
  const [serialCommand, setSerialCommand] = useState('')
  const [serialHistory, setSerialHistory] = useState<Array<{ type: 'cmd' | 'resp' | 'error'; text: string; time: string }>>([])
  const [serialLoading, setSerialLoading] = useState(false)
  const [mainConnectionPort, setMainConnectionPort] = useState<string | null>(null)
  const serialOutputRef = useRef<HTMLDivElement>(null)
  const serialInputRef = useRef<HTMLInputElement>(null)

  // Connect to status WebSocket to get current speed and playback status
  useEffect(() => {
    let ws: WebSocket | null = null
    let shouldReconnect = true

    const connect = () => {
      if (!shouldReconnect) return

      // Don't interrupt an existing connection that's still connecting
      if (ws) {
        if (ws.readyState === WebSocket.CONNECTING) {
          return // Already connecting, wait for it
        }
        if (ws.readyState === WebSocket.OPEN) {
          ws.close()
        }
        ws = null
      }

      ws = new WebSocket(apiClient.getWebSocketUrl('/ws/status'))

      ws.onopen = () => {
        if (!shouldReconnect) {
          // Component unmounted while connecting - close the WebSocket now
          ws?.close()
        }
      }

      ws.onmessage = (event) => {
        if (!shouldReconnect) return
        try {
          const message = JSON.parse(event.data)
          if (message.type === 'status_update' && message.data) {
            if (message.data.speed !== null && message.data.speed !== undefined) {
              setCurrentSpeed(message.data.speed)
            }
            // Track if a pattern is running or paused
            setIsPatternRunning(message.data.is_running || message.data.is_paused)
          }
        } catch (error) {
          console.error('Failed to parse status:', error)
        }
      }
    }

    connect()

    // Reconnect when table changes
    const unsubscribe = apiClient.onBaseUrlChange(() => {
      connect()
    })

    return () => {
      shouldReconnect = false
      unsubscribe()
      if (ws) {
        // Only close if already OPEN - CONNECTING WebSockets will close in onopen
        if (ws.readyState === WebSocket.OPEN) {
          ws.close()
        }
        ws = null
      }
    }
  }, [])

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
    if (checkPatternRunning('home')) return
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
      toast.error('Failed to stop execution')
    }
  }

  const handleSoftReset = async () => {
    try {
      await handleAction('reset', '/soft_reset')
      toast.success('Reset sent. Homing required.')
    } catch {
      toast.error('Failed to send reset')
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

  // Serial terminal functions
  const fetchSerialPorts = async () => {
    try {
      const data = await apiClient.get<string[]>('/list_serial_ports')
      setSerialPorts(Array.isArray(data) ? data : [])
    } catch {
      toast.error('Failed to fetch serial ports')
    }
  }

  const fetchMainConnectionStatus = async () => {
    try {
      const data = await apiClient.get<{ connected: boolean; port?: string }>('/serial_status')
      if (data.connected && data.port) {
        setMainConnectionPort(data.port)
        // Auto-select the connected port
        setSelectedSerialPort(data.port)
      }
    } catch {
      // Ignore errors
    }
  }

  const handleSerialConnect = async () => {
    if (!selectedSerialPort) {
      toast.error('Please select a serial port')
      return
    }
    setSerialLoading(true)
    try {
      await apiClient.post('/api/debug-serial/open', { port: selectedSerialPort })
      setSerialConnected(true)
      addSerialHistory('resp', `Connected to ${selectedSerialPort}`)
      toast.success(`Connected to ${selectedSerialPort}`)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Unknown error'
      addSerialHistory('error', `Failed to connect: ${errorMsg}`)
      toast.error('Failed to connect to serial port')
    } finally {
      setSerialLoading(false)
    }
  }

  const handleSerialDisconnect = async () => {
    setSerialLoading(true)
    try {
      await apiClient.post('/api/debug-serial/close', { port: selectedSerialPort })
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

  const handleSerialSend = async () => {
    if (!serialCommand.trim() || !serialConnected || serialLoading) return

    const cmd = serialCommand.trim()
    setSerialCommand('')
    setSerialLoading(true)
    addSerialHistory('cmd', cmd)

    try {
      const data = await apiClient.post<{ responses?: string[]; detail?: string }>('/api/debug-serial/send', { port: selectedSerialPort, command: cmd })
      if (data.responses) {
        if (data.responses.length > 0) {
          data.responses.forEach((line: string) => addSerialHistory('resp', line))
        } else {
          addSerialHistory('resp', '(no response)')
        }
      } else if (data.detail) {
        addSerialHistory('error', data.detail || 'Command failed')
      }
    } catch (error) {
      addSerialHistory('error', `Error: ${error}`)
    } finally {
      setSerialLoading(false)
      setTimeout(() => serialInputRef.current?.focus(), 0)
    }
  }

  const handleSerialReset = async () => {
    if (!serialConnected || serialLoading) return

    setSerialLoading(true)
    addSerialHistory('cmd', '[Ctrl+X] Soft Reset')

    try {
      // Send Ctrl+X (0x18) - GRBL soft reset command
      const data = await apiClient.post<{ responses?: string[]; detail?: string }>('/api/debug-serial/send', { port: selectedSerialPort, command: '\x18' })
      if (data.responses && data.responses.length > 0) {
        data.responses.forEach((line: string) => addSerialHistory('resp', line))
      } else {
        addSerialHistory('resp', 'Reset sent')
      }
      toast.success('Reset command sent')
    } catch (error) {
      addSerialHistory('error', `Reset failed: ${error}`)
      toast.error('Failed to send reset')
    } finally {
      setSerialLoading(false)
    }
  }

  const handleSerialKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (!serialLoading) {
        handleSerialSend()
      }
    }
  }

  // Fetch serial ports and main connection status on mount
  useEffect(() => {
    fetchSerialPorts()
    fetchMainConnectionStatus()
  }, [])

  // Auto-connect to the main connection port
  useEffect(() => {
    if (mainConnectionPort && selectedSerialPort === mainConnectionPort && !serialConnected && !serialLoading) {
      handleSerialConnect()
    }
  }, [mainConnectionPort, selectedSerialPort])

  return (
    <TooltipProvider>
      <div className="flex flex-col w-full max-w-5xl mx-auto gap-6 py-3 sm:py-6 px-0 sm:px-4">
        {/* Page Header */}
        <div className="space-y-0.5 sm:space-y-1 pl-1">
          <h1 className="text-xl font-semibold tracking-tight">Table Control</h1>
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

                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      onClick={handleSoftReset}
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
                  </TooltipTrigger>
                  <TooltipContent>Reset DLC32/ESP32, requires homing</TooltipContent>
                </Tooltip>
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

                    <Alert className="flex items-start border-amber-500/50">
                      <span className="material-icons-outlined text-amber-500 text-base mr-2 shrink-0">
                        warning
                      </span>
                      <AlertDescription className="text-amber-600 dark:text-amber-400">
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
                      <span className="text-xs">Clear Sideway</span>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Clear with side-to-side motion</TooltipContent>
                </Tooltip>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Serial Terminal */}
        <Card className="transition-all duration-200 hover:shadow-md hover:border-primary/20">
          <CardHeader className="pb-3 space-y-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <CardTitle className="text-lg flex items-center gap-2">
                  <span className="material-icons-outlined text-xl">terminal</span>
                  Serial Terminal
                </CardTitle>
                <CardDescription className="hidden sm:block">Send raw commands to the table controller</CardDescription>
              </div>
              {/* Clear button - only show on desktop in header */}
              <div className="hidden sm:flex items-center gap-1">
                {serialHistory.length > 0 && (
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setSerialHistory([])}
                    title="Clear history"
                  >
                    <span className="material-icons-outlined">delete_sweep</span>
                  </Button>
                )}
              </div>
            </div>
            {/* Controls row - stacks better on mobile */}
            <div className="flex flex-wrap items-center gap-2">
              {/* Port selector - auto-refreshes on focus */}
              <select
                className="h-9 flex-1 min-w-[140px] max-w-[200px] rounded-full border border-input bg-background px-4 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring"
                value={selectedSerialPort}
                onChange={(e) => setSelectedSerialPort(e.target.value)}
                onFocus={fetchSerialPorts}
                disabled={serialConnected || serialLoading}
              >
                <option value="">Select port...</option>
                {serialPorts.map((port) => (
                  <option key={port} value={port}>{port}</option>
                ))}
              </select>
              {!serialConnected ? (
                <Button
                  size="sm"
                  onClick={handleSerialConnect}
                  disabled={!selectedSerialPort || serialLoading}
                  title="Connect"
                >
                  {serialLoading ? (
                    <span className="material-icons-outlined animate-spin sm:mr-1">sync</span>
                  ) : (
                    <span className="material-icons-outlined sm:mr-1">power</span>
                  )}
                  <span className="hidden sm:inline">Connect</span>
                </Button>
              ) : (
                <>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={handleSerialDisconnect}
                    disabled={serialLoading}
                    title="Disconnect"
                  >
                    <span className="material-icons-outlined sm:mr-1">power_off</span>
                    <span className="hidden sm:inline">Disconnect</span>
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={handleSerialReset}
                    disabled={serialLoading}
                    title="Send Ctrl+X soft reset"
                  >
                    <span className="material-icons-outlined sm:mr-1">restart_alt</span>
                    <span className="hidden sm:inline">Reset</span>
                  </Button>
                </>
              )}
              {/* Clear button - show on mobile in controls row */}
              {serialHistory.length > 0 && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="sm:hidden"
                  onClick={() => setSerialHistory([])}
                  title="Clear history"
                >
                  <span className="material-icons-outlined">delete</span>
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {/* Output area */}
            <div
              ref={serialOutputRef}
              className="bg-black/90 rounded-md p-3 h-48 overflow-y-auto font-mono text-sm mb-3"
            >
              {serialHistory.length > 0 ? (
                serialHistory.map((entry, i) => (
                  <div
                    key={i}
                    className={`${
                      entry.type === 'cmd'
                        ? 'text-cyan-400'
                        : entry.type === 'error'
                          ? 'text-red-400'
                          : 'text-green-400'
                    }`}
                  >
                    <span className="text-gray-500 text-xs mr-2">{entry.time}</span>
                    {entry.type === 'cmd' ? '> ' : ''}
                    {entry.text}
                  </div>
                ))
              ) : (
                <div className="text-gray-500 italic">
                  {serialConnected
                    ? 'Ready. Enter a command below (e.g., $, $$, ?, $H)'
                    : 'Connect to a serial port to send commands'}
                </div>
              )}
            </div>

            {/* Input area */}
            <div className="flex gap-2">
              <Input
                ref={serialInputRef}
                value={serialCommand}
                onChange={(e) => setSerialCommand(e.target.value)}
                onKeyDown={handleSerialKeyDown}
                disabled={!serialConnected}
                readOnly={serialLoading}
                placeholder={serialConnected ? 'Enter command (e.g., $, $$, ?, $H)' : 'Connect to send commands'}
                className="font-mono text-base h-11"
              />
              <Button
                onClick={handleSerialSend}
                disabled={!serialConnected || !serialCommand.trim() || serialLoading}
                className="h-11 px-6"
              >
                {serialLoading ? (
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
