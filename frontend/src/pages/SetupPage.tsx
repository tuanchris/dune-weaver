import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { apiClient } from '@/lib/apiClient'
import { useStatusStore } from '@/stores/useStatusStore'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'

// ─── Types ───────────────────────────────────────────────────────────────────

interface AxisConfig {
  steps_per_mm: number | null
  max_rate_mm_per_min: number | null
  acceleration_mm_per_sec2: number | null
  direction_pin: string | null
  direction_inverted: boolean | null
  homing_cycle: number | null
  homing_positive_direction: boolean | null
  homing_mpos_mm: number | null
  homing_feed_mm_per_min: number | null
  homing_seek_mm_per_min: number | null
  homing_settle_ms: number | null
  homing_seek_scaler: number | null
  homing_feed_scaler: number | null
  hard_limits: boolean | null
  pulloff_mm: number | null
}

interface FluidNCConfig {
  axes: { x: AxisConfig; y: AxisConfig }
  start: { must_home: boolean | null }
}

// ─── Calibration Wizard ──────────────────────────────────────────────────────

type WizardStep =
  | 'precheck'
  | 'home'
  | 'test-y'
  | 'test-x'
  | 'fix'
  | 'sanity-y'
  | 'sanity-x'
  | 'dip-check'
  | 'complete'

interface WizardState {
  step: WizardStep
  yCorrect: boolean | null
  xCorrect: boolean | null
  sending: boolean
  fixing: boolean
}

const WIZARD_STEPS: { key: WizardStep; label: string }[] = [
  { key: 'precheck', label: 'Pre-check' },
  { key: 'home', label: 'Home' },
  { key: 'test-y', label: 'Test Y' },
  { key: 'test-x', label: 'Test X' },
  { key: 'fix', label: 'Fix' },
  { key: 'sanity-y', label: 'Verify Y' },
  { key: 'sanity-x', label: 'Verify X' },
  { key: 'complete', label: 'Done' },
]

function getStepIndex(step: WizardStep): number {
  return WIZARD_STEPS.findIndex((s) => s.key === step)
}

function CalibrationWizard() {
  const isConnected = useStatusStore((s) => s.status?.connection_status ?? false)
  const isRunning = useStatusStore((s) => s.status?.is_running ?? false)

  const [wizard, setWizard] = useState<WizardState>({
    step: 'precheck',
    yCorrect: null,
    xCorrect: null,
    sending: false,
    fixing: false,
  })

  const sendCommand = useCallback(async (command: string, manageSending = true) => {
    if (manageSending) setWizard((w) => ({ ...w, sending: true }))
    try {
      const res = await apiClient.post<{ success: boolean; responses: string[] }>(
        '/api/fluidnc/command',
        { command }
      )
      if (!res.success) {
        toast.error('Command failed')
      }
    } catch (err) {
      toast.error(`Error: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      if (manageSending) setWizard((w) => ({ ...w, sending: false }))
    }
  }, [])

  const fixDirection = useCallback(
    async (axis: 'x' | 'y') => {
      setWizard((w) => ({ ...w, fixing: true }))
      try {
        // Toggle direction, save config
        await apiClient.patch('/api/fluidnc/config', {
          axes: { [axis]: { direction_inverted: true } },
        })
        toast.success(`${axis.toUpperCase()} direction toggled and saved`)
      } catch (err) {
        toast.error(`Fix failed: ${err instanceof Error ? err.message : 'Unknown'}`)
      } finally {
        setWizard((w) => ({ ...w, fixing: false }))
      }
    },
    []
  )

  const restartController = useCallback(async () => {
    setWizard((w) => ({ ...w, fixing: true }))
    try {
      await apiClient.post('/api/fluidnc/command', { command: '$Bye', timeout: 2.0 })
      toast.success('Restart command sent. Reconnect when ready.')
    } catch {
      // $Bye causes disconnect, so errors are expected
      toast.info('Restart command sent. The controller will reboot.')
    } finally {
      setWizard((w) => ({ ...w, fixing: false }))
    }
  }, [])

  const waitForIdle = useCallback(async (timeoutMs = 30000) => {
    const start = Date.now()
    while (Date.now() - start < timeoutMs) {
      await new Promise((r) => setTimeout(r, 1000))
      try {
        const res = await apiClient.post<{ success: boolean; responses: string[] }>(
          '/api/fluidnc/command',
          { command: '?', timeout: 2.0 }
        )
        if (res.responses?.some((r) => r.includes('Idle'))) return true
      } catch {
        // Ignore poll errors
      }
    }
    return false
  }, [])

  const reset = () =>
    setWizard({ step: 'precheck', yCorrect: null, xCorrect: null, sending: false, fixing: false })

  const currentIndex = getStepIndex(wizard.step)

  const canProceedFromPrecheck = isConnected && !isRunning

  return (
    <div className="space-y-6">
      {/* Step indicator */}
      <div className="flex items-center gap-1 overflow-x-auto pb-2">
        {WIZARD_STEPS.map((s, i) => (
          <div key={s.key} className="flex items-center gap-1">
            <button
              type="button"
              title={s.label}
              onClick={() => setWizard((w) => ({ ...w, step: s.key }))}
              className={`flex items-center justify-center w-7 h-7 rounded-full text-xs font-medium shrink-0 cursor-pointer transition-opacity hover:opacity-80 ${
                i < currentIndex
                  ? 'bg-primary text-primary-foreground'
                  : i === currentIndex
                    ? 'bg-primary text-primary-foreground ring-2 ring-primary/30'
                    : 'bg-muted text-muted-foreground'
              }`}
            >
              {i < currentIndex ? (
                <span className="material-icons-outlined text-sm">check</span>
              ) : (
                i + 1
              )}
            </button>
            {i < WIZARD_STEPS.length - 1 && (
              <div
                className={`w-4 h-0.5 ${i < currentIndex ? 'bg-primary' : 'bg-muted'}`}
              />
            )}
          </div>
        ))}
      </div>

      {/* Step content */}
      {wizard.step === 'precheck' && (
        <div className="space-y-4">
          <h3 className="font-semibold">Pre-check</h3>
          <p className="text-sm text-muted-foreground">
            Verify the table is connected and no pattern is running before calibrating motor directions.
          </p>
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span
                className={`material-icons-outlined text-base ${isConnected ? 'text-green-500' : 'text-red-500'}`}
              >
                {isConnected ? 'check_circle' : 'cancel'}
              </span>
              <span className="text-sm">Controller connected</span>
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`material-icons-outlined text-base ${!isRunning ? 'text-green-500' : 'text-red-500'}`}
              >
                {!isRunning ? 'check_circle' : 'cancel'}
              </span>
              <span className="text-sm">No pattern running</span>
            </div>
          </div>
          <Button
            onClick={() => setWizard((w) => ({ ...w, step: 'home' }))}
            disabled={!canProceedFromPrecheck}
          >
            Begin Calibration
          </Button>
        </div>
      )}

      {wizard.step === 'home' && (
        <div className="space-y-4">
          <h3 className="font-semibold">Home Table</h3>
          <p className="text-sm text-muted-foreground">
            Home the table to establish a known position before testing motor directions.
            The ball will move to the home position.
          </p>
          <div className="flex gap-3">
            <Button
              onClick={async () => {
                setWizard((w) => ({ ...w, sending: true }))
                try {
                  await apiClient.post('/send_home')
                  toast.success('Homing complete')
                  setWizard((w) => ({ ...w, sending: false, step: 'test-y' }))
                } catch (err) {
                  toast.error(`Homing failed: ${err instanceof Error ? err.message : 'Unknown error'}`)
                  setWizard((w) => ({ ...w, sending: false }))
                }
              }}
              disabled={wizard.sending}
            >
              {wizard.sending ? (
                <span className="material-icons-outlined animate-spin mr-2 text-base">sync</span>
              ) : (
                <span className="material-icons-outlined mr-2 text-base">home</span>
              )}
              {wizard.sending ? 'Homing...' : 'Home Table'}
            </Button>
            <Button
              variant="outline"
              onClick={() => setWizard((w) => ({ ...w, step: 'test-y' }))}
              disabled={wizard.sending}
            >
              Skip
            </Button>
          </div>
        </div>
      )}

      {wizard.step === 'test-y' && (
        <div className="space-y-4">
          <h3 className="font-semibold">Test Y Axis (Radial)</h3>
          <p className="text-sm text-muted-foreground">
            This sends a small radial movement. Watch the ball and answer whether it moved <strong>outward</strong> (toward the perimeter).
          </p>
          <Button onClick={() => sendCommand('$J=G91 G21 Y5 F100.0')} disabled={wizard.sending}>
            {wizard.sending ? (
              <span className="material-icons-outlined animate-spin mr-2 text-base">sync</span>
            ) : (
              <span className="material-icons-outlined mr-2 text-base">play_arrow</span>
            )}
            Send Test Command
          </Button>
          <div className="flex gap-3 pt-2">
            <Button
              variant="outline"
              onClick={() => setWizard((w) => ({ ...w, yCorrect: true, step: 'test-x' }))}
              disabled={wizard.sending}
            >
              <span className="material-icons-outlined mr-1 text-base text-green-500">thumb_up</span>
              Yes, moved outward
            </Button>
            <Button
              variant="outline"
              onClick={() => setWizard((w) => ({ ...w, yCorrect: false, step: 'test-x' }))}
              disabled={wizard.sending}
            >
              <span className="material-icons-outlined mr-1 text-base text-red-500">thumb_down</span>
              No, moved inward
            </Button>
          </div>
        </div>
      )}

      {wizard.step === 'test-x' && (
        <div className="space-y-4">
          <h3 className="font-semibold">Test X Axis (Angular)</h3>
          <p className="text-sm text-muted-foreground">
            This sends a small angular movement. Watch the ball and answer whether it moved <strong>clockwise</strong> when viewed from above.
          </p>
          <Button onClick={() => sendCommand('$J=G91 G21 X5 F100.0')} disabled={wizard.sending}>
            {wizard.sending ? (
              <span className="material-icons-outlined animate-spin mr-2 text-base">sync</span>
            ) : (
              <span className="material-icons-outlined mr-2 text-base">play_arrow</span>
            )}
            Send Test Command
          </Button>
          <div className="flex gap-3 pt-2">
            <Button
              variant="outline"
              onClick={() => {
                setWizard((w) => ({
                  ...w,
                  xCorrect: true,
                  step: w.yCorrect === false ? 'fix' : 'sanity-y',
                }))
              }}
              disabled={wizard.sending}
            >
              <span className="material-icons-outlined mr-1 text-base text-green-500">thumb_up</span>
              Yes, moved clockwise
            </Button>
            <Button
              variant="outline"
              onClick={() => setWizard((w) => ({ ...w, xCorrect: false, step: 'fix' }))}
              disabled={wizard.sending}
            >
              <span className="material-icons-outlined mr-1 text-base text-red-500">thumb_down</span>
              No, moved counter-clockwise
            </Button>
          </div>
        </div>
      )}

      {wizard.step === 'fix' && (
        <div className="space-y-4">
          <h3 className="font-semibold">Fix Motor Directions</h3>
          <p className="text-sm text-muted-foreground">
            The following axes need their direction inverted. Click to auto-fix by toggling the <code>:low</code> flag on the direction pin.
          </p>
          <div className="space-y-3">
            {wizard.yCorrect === false && (
              <div className="flex items-center justify-between p-3 rounded-lg border">
                <div>
                  <p className="font-medium text-sm">Y Axis (Radial)</p>
                  <p className="text-xs text-muted-foreground">Direction is inverted</p>
                </div>
                <Button
                  size="sm"
                  onClick={() => fixDirection('y')}
                  disabled={wizard.fixing}
                >
                  {wizard.fixing ? 'Fixing...' : 'Fix Automatically'}
                </Button>
              </div>
            )}
            {wizard.xCorrect === false && (
              <div className="flex items-center justify-between p-3 rounded-lg border">
                <div>
                  <p className="font-medium text-sm">X Axis (Angular)</p>
                  <p className="text-xs text-muted-foreground">Direction is inverted</p>
                </div>
                <Button
                  size="sm"
                  onClick={() => fixDirection('x')}
                  disabled={wizard.fixing}
                >
                  {wizard.fixing ? 'Fixing...' : 'Fix Automatically'}
                </Button>
              </div>
            )}
          </div>
          <Alert>
            <span className="material-icons-outlined text-base mr-2 shrink-0">warning</span>
            <AlertDescription>
              Direction pin changes require a controller restart to take effect. After fixing, restart the controller below, then re-run the wizard to verify.
            </AlertDescription>
          </Alert>
          <div className="flex gap-3">
            <Button variant="outline" onClick={restartController} disabled={wizard.fixing}>
              <span className="material-icons-outlined mr-2 text-base">restart_alt</span>
              Restart Controller
            </Button>
            <Button onClick={() => setWizard((w) => ({ ...w, step: 'sanity-y' }))}>
              Continue to Verification
            </Button>
          </div>
        </div>
      )}

      {wizard.step === 'sanity-y' && (
        <div className="space-y-4">
          <h3 className="font-semibold">Verify Y Axis (Larger Movement)</h3>
          <p className="text-sm text-muted-foreground">
            This moves the ball to center first, then sends a longer radial movement. The ball should move clearly from <strong>center toward the perimeter</strong>.
          </p>
          <Button
            onClick={async () => {
              setWizard((w) => ({ ...w, sending: true }))
              try {
                await apiClient.post('/move_to_center')
                await waitForIdle(60000)
                await sendCommand('$J=G91 G21 Y20 F100.0', false)
                await waitForIdle()
              } finally {
                setWizard((w) => ({ ...w, sending: false }))
              }
            }}
            disabled={wizard.sending}
          >
            {wizard.sending ? (
              <span className="material-icons-outlined animate-spin mr-2 text-base">sync</span>
            ) : (
              <span className="material-icons-outlined mr-2 text-base">play_arrow</span>
            )}
            {wizard.sending ? 'Moving...' : 'Send Verification Command'}
          </Button>
          <div className="flex flex-wrap gap-3 pt-2">
            <Button
              onClick={() => setWizard((w) => ({ ...w, step: 'sanity-x' }))}
              disabled={wizard.sending}
            >
              <span className="material-icons-outlined mr-1 text-base text-green-500">check</span>
              Looks Correct
            </Button>
            <Button
              variant="outline"
              onClick={() => setWizard((w) => ({ ...w, step: 'dip-check' }))}
              disabled={wizard.sending}
            >
              <span className="material-icons-outlined mr-1 text-base text-amber-500">warning</span>
              Only Moved Halfway
            </Button>
            <Button
              variant="outline"
              onClick={reset}
              disabled={wizard.sending}
            >
              Start Over
            </Button>
          </div>
        </div>
      )}

      {wizard.step === 'sanity-x' && (
        <div className="space-y-4">
          <h3 className="font-semibold">Verify X Axis (Larger Movement)</h3>
          <p className="text-sm text-muted-foreground">
            This sends a larger angular movement. The ball should make roughly a <strong>full clockwise rotation</strong>.
            It will also spiral inward slightly — this is normal due to the mechanical coupling between the angular and radial axes.
          </p>
          <Button
            onClick={async () => {
              setWizard((w) => ({ ...w, sending: true }))
              try {
                await sendCommand('$J=G91 G21 X50 F100.0', false)
                await waitForIdle()
              } finally {
                setWizard((w) => ({ ...w, sending: false }))
              }
            }}
            disabled={wizard.sending}
          >
            {wizard.sending ? (
              <span className="material-icons-outlined animate-spin mr-2 text-base">sync</span>
            ) : (
              <span className="material-icons-outlined mr-2 text-base">play_arrow</span>
            )}
            {wizard.sending ? 'Moving...' : 'Send Verification Command'}
          </Button>
          <div className="flex flex-wrap gap-3 pt-2">
            <Button
              onClick={() => setWizard((w) => ({ ...w, step: 'complete' }))}
              disabled={wizard.sending}
            >
              <span className="material-icons-outlined mr-1 text-base text-green-500">check</span>
              Looks Correct
            </Button>
            <Button
              variant="outline"
              onClick={() => setWizard((w) => ({ ...w, step: 'dip-check' }))}
              disabled={wizard.sending}
            >
              <span className="material-icons-outlined mr-1 text-base text-amber-500">warning</span>
              Only Half a Revolution
            </Button>
            <Button
              variant="outline"
              onClick={reset}
              disabled={wizard.sending}
            >
              Start Over
            </Button>
          </div>
        </div>
      )}

      {wizard.step === 'dip-check' && (
        <div className="space-y-4">
          <h3 className="font-semibold">Check DIP Switches</h3>
          <Alert variant="destructive">
            <span className="material-icons-outlined text-base mr-2 shrink-0">power_off</span>
            <AlertDescription>
              <strong>Turn off the table completely</strong> before touching any hardware. Disconnect power before checking DIP switches.
            </AlertDescription>
          </Alert>
          <p className="text-sm text-muted-foreground">
            If the ball only moved <strong>half the expected distance</strong>, the stepper driver microstepping DIP switches are likely misconfigured.
          </p>
          <div className="rounded-lg border p-4 space-y-3 bg-muted/30">
            <p className="text-sm font-medium">How to fix:</p>
            <ol className="text-sm text-muted-foreground list-decimal list-inside space-y-2">
              <li>Power off the table completely</li>
              <li>Locate the DIP switches underneath each stepper driver</li>
              <li>Set <strong>all DIP switches to OFF</strong> (this selects full-step or the driver's default microstepping)</li>
              <li>Power the table back on and re-run the calibration wizard</li>
            </ol>
          </div>
          <div className="flex gap-3">
            <Button variant="outline" onClick={reset}>
              Restart Wizard
            </Button>
          </div>
        </div>
      )}

      {wizard.step === 'complete' && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-green-600">
            <span className="material-icons-outlined text-2xl">check_circle</span>
            <h3 className="font-semibold text-lg">Calibration Complete</h3>
          </div>
          <p className="text-sm text-muted-foreground">
            Both axes are moving in the correct directions. Your table is ready to use.
          </p>
          <Button variant="outline" onClick={reset}>
            Run Again
          </Button>
        </div>
      )}
    </div>
  )
}

// ─── FluidNC Config Editor ───────────────────────────────────────────────────

const MOVEMENT_FIELDS: { key: keyof AxisConfig; label: string; unit: string }[] = [
  { key: 'steps_per_mm', label: 'Steps per mm', unit: 'steps' },
  { key: 'max_rate_mm_per_min', label: 'Max Rate', unit: 'mm/min' },
  { key: 'acceleration_mm_per_sec2', label: 'Acceleration', unit: 'mm/s²' },
]

const HOMING_NUMBER_FIELDS: { key: keyof AxisConfig; label: string; unit: string }[] = [
  { key: 'homing_cycle', label: 'Homing Cycle', unit: '-1 = disabled' },
  { key: 'homing_mpos_mm', label: 'Homing MPos', unit: 'mm' },
  { key: 'homing_feed_mm_per_min', label: 'Homing Feed Rate', unit: 'mm/min' },
  { key: 'homing_seek_mm_per_min', label: 'Homing Seek Rate', unit: 'mm/min' },
  { key: 'homing_settle_ms', label: 'Homing Settle Time', unit: 'ms' },
  { key: 'homing_seek_scaler', label: 'Homing Seek Scaler', unit: '' },
  { key: 'homing_feed_scaler', label: 'Homing Feed Scaler', unit: '' },
  { key: 'pulloff_mm', label: 'Pulloff Distance', unit: 'mm' },
]

const HOMING_BOOL_FIELDS: { key: keyof AxisConfig; label: string }[] = [
  { key: 'homing_positive_direction', label: 'Positive Direction' },
]

function ConfigEditor() {
  const isConnected = useStatusStore((s) => s.status?.connection_status ?? false)

  const [config, setConfig] = useState<FluidNCConfig | null>(null)
  const [original, setOriginal] = useState<FluidNCConfig | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const readConfig = useCallback(async () => {
    setLoading(true)
    try {
      const res = await apiClient.get<{ success: boolean; settings: FluidNCConfig }>(
        '/api/fluidnc/config'
      )
      if (res.success) {
        setConfig(res.settings)
        setOriginal(structuredClone(res.settings))
        toast.success('Configuration loaded from controller')
      }
    } catch (err) {
      toast.error(`Failed to read config: ${err instanceof Error ? err.message : 'Unknown'}`)
    } finally {
      setLoading(false)
    }
  }, [])

  const saveConfig = useCallback(async () => {
    if (!config || !original) return
    setSaving(true)
    try {
      // Build diff: only send changed fields
      const update: { axes?: Record<string, Record<string, unknown>>; start?: Record<string, unknown> } = {}

      for (const axis of ['x', 'y'] as const) {
        const changes: Record<string, unknown> = {}
        const curr = config.axes[axis]
        const orig = original.axes[axis]
        for (const key of Object.keys(curr) as (keyof AxisConfig)[]) {
          if (key === 'direction_pin') continue // raw pin, skip
          if (curr[key] !== orig[key] && curr[key] !== null) {
            changes[key] = curr[key]
          }
        }
        if (Object.keys(changes).length > 0) {
          if (!update.axes) update.axes = {}
          update.axes[axis] = changes
        }
      }

      if (config.start.must_home !== original.start.must_home && config.start.must_home !== null) {
        update.start = { must_home: config.start.must_home }
      }

      if (!update.axes && !update.start) {
        toast.info('No changes to save')
        setSaving(false)
        return
      }

      const res = await apiClient.patch<{
        success: boolean
        saved: boolean
        changes_applied: string[]
        restart_required: boolean
      }>('/api/fluidnc/config', update)

      if (res.success) {
        setOriginal(structuredClone(config))
        if (res.restart_required) {
          toast.warning('Settings saved. Direction pin changes require a controller restart.')
        } else if (res.saved) {
          toast.success(`Saved ${res.changes_applied.length} setting(s) to controller`)
        } else {
          toast.warning('Settings applied but flash save may have failed')
        }
      }
    } catch (err) {
      toast.error(`Save failed: ${err instanceof Error ? err.message : 'Unknown'}`)
    } finally {
      setSaving(false)
    }
  }, [config, original])

  const updateAxis = (axis: 'x' | 'y', key: keyof AxisConfig, value: unknown) => {
    setConfig((prev) => {
      if (!prev) return prev
      return {
        ...prev,
        axes: {
          ...prev.axes,
          [axis]: { ...prev.axes[axis], [key]: value },
        },
      }
    })
  }

  const hasChanges =
    config && original ? JSON.stringify(config) !== JSON.stringify(original) : false

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button onClick={readConfig} disabled={loading || !isConnected}>
          {loading ? (
            <span className="material-icons-outlined animate-spin mr-2 text-base">sync</span>
          ) : (
            <span className="material-icons-outlined mr-2 text-base">download</span>
          )}
          {loading ? 'Reading...' : 'Read from Controller'}
        </Button>
        {config && (
          <Button onClick={saveConfig} disabled={saving || !hasChanges}>
            {saving ? (
              <span className="material-icons-outlined animate-spin mr-2 text-base">sync</span>
            ) : (
              <span className="material-icons-outlined mr-2 text-base">save</span>
            )}
            {saving ? 'Saving...' : 'Save to Controller'}
          </Button>
        )}
        {hasChanges && (
          <Badge variant="secondary">Unsaved changes</Badge>
        )}
      </div>

      {!isConnected && (
        <Alert>
          <span className="material-icons-outlined text-base mr-2 shrink-0">link_off</span>
          <AlertDescription>
            Connect to a controller first to read or modify FluidNC settings.
          </AlertDescription>
        </Alert>
      )}

      {config && (
        <Accordion type="multiple" defaultValue={['axis-x', 'axis-y']}>
          {/* Per-axis sections */}
          {(['x', 'y'] as const).map((axis) => (
            <AccordionItem key={axis} value={`axis-${axis}`} className="border rounded-lg px-4 mt-2 bg-card">
              <AccordionTrigger className="hover:no-underline">
                <div className="flex items-center gap-3">
                  <span className="material-icons-outlined text-muted-foreground">
                    {axis === 'x' ? 'rotate_right' : 'swap_vert'}
                  </span>
                  <div className="text-left">
                    <div className="font-semibold">
                      {axis.toUpperCase()} Axis — {axis === 'x' ? 'Angular' : 'Radial'}
                    </div>
                    <div className="text-sm text-muted-foreground font-normal">
                      Movement, direction, and homing for the {axis === 'x' ? 'angular' : 'radial'} motor
                    </div>
                  </div>
                </div>
              </AccordionTrigger>
              <AccordionContent className="pt-4 pb-6 space-y-6">
                {/* Movement */}
                <div className="space-y-3">
                  <Label className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Movement</Label>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    {MOVEMENT_FIELDS.map((field) => (
                      <div key={field.key} className="space-y-1">
                        <Label className="text-xs text-muted-foreground">{field.label}</Label>
                        <Input
                          type="number"
                          step="any"
                          value={(config.axes[axis][field.key] as number | null) ?? ''}
                          onChange={(e) =>
                            updateAxis(
                              axis,
                              field.key,
                              e.target.value ? parseFloat(e.target.value) : null
                            )
                          }
                          placeholder={field.unit}
                        />
                      </div>
                    ))}
                  </div>
                </div>

                <Separator />

                {/* Direction */}
                <div className="space-y-3">
                  <Label className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Direction</Label>
                  <div className="flex items-center justify-between p-3 rounded-lg border">
                    <div>
                      {config.axes[axis].direction_pin !== null ? (
                        <p className="text-xs text-muted-foreground font-mono">
                          Pin: {config.axes[axis].direction_pin}
                        </p>
                      ) : (
                        <p className="text-xs text-muted-foreground">
                          Not available (may not be a stepstick driver)
                        </p>
                      )}
                    </div>
                    {config.axes[axis].direction_inverted !== null && (
                      <div className="flex items-center gap-2">
                        <Label className="text-sm">Inverted</Label>
                        <Switch
                          checked={config.axes[axis].direction_inverted ?? false}
                          onCheckedChange={(checked) =>
                            updateAxis(axis, 'direction_inverted', checked)
                          }
                        />
                      </div>
                    )}
                  </div>
                </div>

                <Separator />

                {/* Homing */}
                <div className="space-y-3">
                  <Label className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Homing</Label>
                  <div className="space-y-3">
                    {HOMING_BOOL_FIELDS.map((field) => (
                      <div
                        key={field.key}
                        className="flex items-center justify-between p-2 rounded-lg border"
                      >
                        <Label className="text-sm">{field.label}</Label>
                        <Switch
                          checked={(config.axes[axis][field.key] as boolean) ?? false}
                          onCheckedChange={(checked) => updateAxis(axis, field.key, checked)}
                        />
                      </div>
                    ))}
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                    {HOMING_NUMBER_FIELDS.map((field) => (
                      <div key={field.key} className="space-y-1">
                        <Label className="text-xs text-muted-foreground">{field.label}</Label>
                        <Input
                          type="number"
                          step="any"
                          value={(config.axes[axis][field.key] as number | null) ?? ''}
                          onChange={(e) =>
                            updateAxis(
                              axis,
                              field.key,
                              e.target.value ? parseFloat(e.target.value) : null
                            )
                          }
                          placeholder={field.unit}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      )}
    </div>
  )
}

// ─── Setup Page ──────────────────────────────────────────────────────────────

export function SetupPage() {
  const navigate = useNavigate()

  return (
    <div className="max-w-4xl mx-auto space-y-6 p-4 pb-32">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate('/settings')}>
          <span className="material-icons-outlined">arrow_back</span>
        </Button>
        <div>
          <h1 className="text-2xl font-bold">Hardware Setup</h1>
          <p className="text-sm text-muted-foreground">
            Calibrate motors and configure FluidNC settings
          </p>
        </div>
      </div>

      {/* Info banner */}
      <Alert>
        <span className="material-icons-outlined text-base mr-2 shrink-0">info</span>
        <AlertDescription>
          This page is for <strong>FluidNC-based boards with bipolar stepper motors</strong> (DLC32, MKS boards).
          Not applicable to unipolar/28BYJ-48 setups.
        </AlertDescription>
      </Alert>

      {/* Main content */}
      <Accordion type="multiple" defaultValue={['calibration', 'config']}>
        <AccordionItem value="calibration" className="border rounded-lg px-4 bg-card">
          <AccordionTrigger className="hover:no-underline">
            <div className="flex items-center gap-3">
              <span className="material-icons-outlined text-muted-foreground">tune</span>
              <div className="text-left">
                <div className="font-semibold">Calibration Wizard</div>
                <div className="text-sm text-muted-foreground font-normal">
                  Verify and fix motor directions step by step
                </div>
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent className="pt-4 pb-6">
            <CalibrationWizard />
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="config" className="border rounded-lg px-4 mt-2 bg-card">
          <AccordionTrigger className="hover:no-underline">
            <div className="flex items-center gap-3">
              <span className="material-icons-outlined text-muted-foreground">settings</span>
              <div className="text-left">
                <div className="font-semibold">FluidNC Configuration</div>
                <div className="text-sm text-muted-foreground font-normal">
                  Read and edit curated controller settings
                </div>
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent className="pt-4 pb-6" forceMount>
            <Alert className="mb-4">
              <span className="material-icons-outlined text-base mr-2 shrink-0">warning</span>
              <AlertDescription>
                These are low-level FluidNC firmware settings. Only modify them if you understand what each parameter does — incorrect values can cause erratic movement or prevent the table from working.
              </AlertDescription>
            </Alert>
            <ConfigEditor />
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  )
}
