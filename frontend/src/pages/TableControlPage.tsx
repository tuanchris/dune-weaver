import { useState, useEffect } from 'react'
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

export function TableControlPage() {
  const [speedInput, setSpeedInput] = useState('')
  const [currentSpeed, setCurrentSpeed] = useState<number | null>(null)
  const [currentTheta, setCurrentTheta] = useState(0)
  const [isLoading, setIsLoading] = useState<string | null>(null)

  // Connect to status WebSocket to get current speed
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/status`)

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        if (message.type === 'status_update' && message.data) {
          if (message.data.speed !== null && message.data.speed !== undefined) {
            setCurrentSpeed(message.data.speed)
          }
        }
      } catch (error) {
        console.error('Failed to parse status:', error)
      }
    }

    return () => {
      ws.close()
    }
  }, [])

  const handleAction = async (
    action: string,
    endpoint: string,
    body?: object
  ) => {
    setIsLoading(action)
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        ...(body && { body: JSON.stringify(body) }),
      })
      const data = await response.json()
      if (data.success || response.ok) {
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
      toast.error('Failed to stop execution')
    }
  }

  const handleMoveToCenter = async () => {
    try {
      await handleAction('center', '/move_to_center')
      toast.success('Moving to center...')
    } catch {
      toast.error('Failed to move to center')
    }
  }

  const handleMoveToPerimeter = async () => {
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

  return (
    <TooltipProvider>
      <div className="flex flex-col w-full max-w-5xl mx-auto gap-6 py-6">
        {/* Page Header */}
        <div className="space-y-1">
          <h1 className="text-3xl font-bold tracking-tight">Table Control</h1>
          <p className="text-muted-foreground">
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
              <div className="grid grid-cols-2 gap-3">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      onClick={handleHome}
                      disabled={isLoading === 'home'}
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
                  <TooltipContent>Emergency stop</TooltipContent>
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
                      variant="outline"
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
                      variant="outline"
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
                          variant="outline"
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
                            variant="outline"
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
                          variant="outline"
                          onClick={() => handleRotate(-10)}
                          disabled={isLoading === 'rotate'}
                        >
                          <span className="material-icons text-lg mr-1">rotate_left</span>
                          CCW 10°
                        </Button>
                        <Button
                          variant="outline"
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
                      variant="outline"
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
                      variant="outline"
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
                      variant="outline"
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
      </div>
    </TooltipProvider>
  )
}
