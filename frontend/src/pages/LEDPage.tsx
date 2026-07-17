import { useState, useEffect, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { apiClient } from '@/lib/apiClient'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { ColorPicker } from '@/components/ui/color-picker'
import { LedRingPreview } from '@/components/LedRingPreview'

// Types
interface LedConfig {
  provider: 'none' | 'wled' | 'board'
  wled_ip?: string
  num_leds?: number
  gpio_pin?: number
}

interface BallParams {
  fgbright: number
  bgbright: number
  size: number
  bg: string
  direction: 'cw' | 'ccw'
  align: number
}

interface DWLedsStatus {
  connected: boolean
  power_on: boolean
  brightness: number
  speed: number
  intensity: number
  current_effect: number
  current_palette: number
  num_leds: number
  gpio_pin: number
  colors: string[]
  ball?: BallParams
  error?: string
}

interface EffectSettings {
  effect_id: number
  palette_id: number
  speed: number
  intensity: number
  color1: string
  color2: string
  color3: string
}

// Which inputs each firmware effect actually uses, keyed by raw effect name.
// Mirrors dune-weaver-mobile's LED_EFFECTS table (src/api/board.ts) so the
// web page shows/hides the same controls as the app.
const EFFECT_INPUTS: Record<string, { color?: boolean; color2?: boolean; palette?: boolean }> = {
  off: {},
  static: { color: true },
  rainbow: { palette: true },
  breathe: { color: true },
  colorloop: { palette: true },
  theater: { color: true },
  scan: { color: true },
  running: { color: true },
  sine: { color: true },
  gradient: { color: true, color2: true },
  sinelon: { palette: true },
  twinkle: { palette: true },
  sparkle: { color: true },
  fire: { palette: true },
  candle: { color: true },
  meteor: { color: true },
  bouncing: { color: true },
  wipe: { color: true, color2: true },
  dualscan: { color: true, color2: true },
  juggle: { palette: true },
  multicomet: { palette: true },
  glitter: { palette: true },
  dissolve: { color: true, color2: true },
  ripple: { palette: true },
  drip: { color: true },
  lightning: {},
  fireworks: { palette: true },
  plasma: { palette: true },
  heartbeat: { color: true },
  strobe: { color: true },
  police: {},
  chase: { color: true, color2: true },
  railway: { color: true, color2: true },
  pacifica: {},
  aurora: {},
  pride: {},
  colorwaves: { palette: true },
  bpm: { palette: true },
  ball: { color: true, color2: true },
}

export function LEDPage() {
  const [ledConfig, setLedConfig] = useState<LedConfig | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  // DW LEDs state
  const [dwStatus, setDwStatus] = useState<DWLedsStatus | null>(null)
  const [effects, setEffects] = useState<[number, string][]>([])
  const [effectNames, setEffectNames] = useState<[number, string][]>([])
  const [palettes, setPalettes] = useState<[number, string][]>([])
  const [brightness, setBrightness] = useState(35)
  const [speed, setSpeed] = useState(128)
  const [speedInput, setSpeedInput] = useState('128')
  const [intensity, setIntensity] = useState(128)
  const [intensityInput, setIntensityInput] = useState('128')
  const [selectedEffect, setSelectedEffect] = useState('')
  const [selectedPalette, setSelectedPalette] = useState('')
  const [color1, setColor1] = useState('#ff0000')
  const [color2, setColor2] = useState('#000000')
  const [color3, setColor3] = useState('#0000ff')

  // Ball tracker (firmware-native 'ball' effect) params
  const [ballFgBright, setBallFgBright] = useState(255)
  const [ballBgBright, setBallBgBright] = useState(255)
  const [ballSize, setBallSize] = useState(3)
  const [ballBg, setBallBg] = useState('static')
  const [ballDirection, setBallDirection] = useState<'cw' | 'ccw'>('cw')
  const [ballAlign, setBallAlign] = useState(0)

  // Ref for debouncing color picker API calls
  const colorDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Last non-ball effect id, so the ball-tracker toggle can restore it
  const lastNonBallEffect = useRef('')

  // LED control mode
  const [controlMode, setControlMode] = useState<'manual' | 'automated'>('automated')

  // Effect automation state
  const [idleEffect, setIdleEffect] = useState<EffectSettings | null>(null)
  const [playingEffect, setPlayingEffect] = useState<EffectSettings | null>(null)
  const [idleTimeoutEnabled, setIdleTimeoutEnabled] = useState(false)
  const [idleTimeoutMinutes, setIdleTimeoutMinutes] = useState(30)
  const [idleTimeoutInput, setIdleTimeoutInput] = useState('30')

  // Fetch LED configuration
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const [configData, settingsData] = await Promise.all([
          apiClient.get<{ provider?: string; wled_ip?: string; dw_led_num_leds?: number; dw_led_gpio_pin?: number }>('/get_led_config'),
          apiClient.get<{ led?: { control_mode?: string } }>('/api/settings'),
        ])
        // Map backend response fields to our interface
        setLedConfig({
          provider: (configData.provider as LedConfig['provider']) || 'none',
          wled_ip: configData.wled_ip,
          num_leds: configData.dw_led_num_leds,
          gpio_pin: configData.dw_led_gpio_pin,
        })
        if (settingsData.led?.control_mode) {
          setControlMode(settingsData.led.control_mode as 'manual' | 'automated')
        }
      } catch (error) {
        console.error('Error fetching LED config:', error)
      } finally {
        setIsLoading(false)
      }
    }
    fetchConfig()
  }, [])

  // Initialize the control panel for the board provider (the table's own ring
  // via the firmware). The /api/dw_leds/* endpoints are the shared LED contract.
  useEffect(() => {
    if (ledConfig?.provider === 'board') {
      fetchDWLedsStatus()
      fetchEffectsAndPalettes()
      fetchEffectSettings()
    }
  }, [ledConfig])

  // Remember the selected effect whenever it isn't the ball tracker
  useEffect(() => {
    const name = effectNames.find(([id]) => String(id) === selectedEffect)?.[1]
    if (name && name !== 'ball') {
      lastNonBallEffect.current = selectedEffect
    }
  }, [selectedEffect, effectNames])

  const fetchDWLedsStatus = async () => {
    try {
      const data = await apiClient.get<DWLedsStatus>('/api/dw_leds/status')
      setDwStatus(data)
      if (data.connected) {
        setBrightness(data.brightness || 35)
        setSpeed(data.speed || 128)
        setSpeedInput(String(data.speed || 128))
        setIntensity(data.intensity || 128)
        setIntensityInput(String(data.intensity || 128))
        setSelectedEffect(String(data.current_effect || 0))
        setSelectedPalette(String(data.current_palette || 0))
        if (data.colors) {
          setColor1(data.colors[0] || '#ff0000')
          setColor2(data.colors[1] || '#000000')
          setColor3(data.colors[2] || '#0000ff')
        }
        if (data.ball) {
          setBallFgBright(data.ball.fgbright ?? 255)
          setBallBgBright(data.ball.bgbright ?? 255)
          setBallSize(data.ball.size ?? 3)
          setBallBg(data.ball.bg || 'static')
          setBallDirection(data.ball.direction === 'ccw' ? 'ccw' : 'cw')
          setBallAlign(data.ball.align ?? 0)
        }
      }
    } catch (error) {
      console.error('Error fetching DW LEDs status:', error)
    }
  }

  // Push one or more ball-tracker params to the firmware (/sand_led).
  const sendBall = async (params: Record<string, number | string>) => {
    try {
      await apiClient.post('/api/dw_leds/ball', params)
    } catch {
      toast.error('Failed to update ball tracker')
    }
  }

  const fetchEffectsAndPalettes = async () => {
    try {
      const [effectsData, palettesData] = await Promise.all([
        apiClient.get<{ effects?: [number, string][]; names?: [number, string][] }>('/api/dw_leds/effects'),
        apiClient.get<{ palettes?: [number, string][] }>('/api/dw_leds/palettes'),
      ])

      if (effectsData.effects) {
        const sorted = [...effectsData.effects].sort((a, b) => a[1].localeCompare(b[1]))
        setEffects(sorted)
      }
      if (effectsData.names) {
        setEffectNames(effectsData.names)
      }
      if (palettesData.palettes) {
        const sorted = [...palettesData.palettes].sort((a, b) => a[1].localeCompare(b[1]))
        setPalettes(sorted)
      }
    } catch (error) {
      console.error('Error fetching effects/palettes:', error)
    }
  }

  const fetchEffectSettings = async () => {
    try {
      const data = await apiClient.get<{ idle_effect?: EffectSettings; playing_effect?: EffectSettings }>('/api/dw_leds/get_effect_settings')
      setIdleEffect(data.idle_effect || null)
      setPlayingEffect(data.playing_effect || null)
    } catch (error) {
      console.error('Error fetching effect settings:', error)
    }
  }

  const handleControlModeChange = async (mode: 'manual' | 'automated') => {
    setControlMode(mode)
    try {
      await apiClient.patch('/api/settings', { led: { control_mode: mode } })
      toast.success(mode === 'manual' ? 'Manual / HA mode' : 'DW Automated mode')
    } catch {
      toast.error('Failed to update control mode')
    }
  }

  const handlePowerToggle = async () => {
    try {
      const data = await apiClient.post<{ connected?: boolean; power_on?: boolean; error?: string }>('/api/dw_leds/power', { state: 2 })
      if (data.connected) {
        toast.success(`Power ${data.power_on ? 'ON' : 'OFF'}`)
        await fetchDWLedsStatus()
      } else {
        toast.error(data.error || 'Failed to toggle power')
      }
    } catch {
      toast.error('Failed to toggle power')
    }
  }

  const handleBrightnessChange = useCallback(async (value: number[]) => {
    setBrightness(value[0])
  }, [])

  const handleBrightnessCommit = async (value: number[]) => {
    try {
      const data = await apiClient.post<{ connected?: boolean }>('/api/dw_leds/brightness', { value: value[0] })
      if (data.connected) {
        toast.success(`Brightness: ${value[0]}%`)
      }
    } catch {
      toast.error('Failed to set brightness')
    }
  }

  const handleSpeedChange = useCallback((value: number[]) => {
    setSpeed(value[0])
    setSpeedInput(String(value[0]))
  }, [])

  const handleSpeedCommit = async (value: number[]) => {
    try {
      await apiClient.post('/api/dw_leds/speed', { speed: value[0] })
      toast.success(`Speed: ${value[0]}`)
    } catch {
      toast.error('Failed to set speed')
    }
  }

  const handleIntensityChange = useCallback((value: number[]) => {
    setIntensity(value[0])
    setIntensityInput(String(value[0]))
  }, [])

  const handleIntensityCommit = async (value: number[]) => {
    try {
      await apiClient.post('/api/dw_leds/intensity', { intensity: value[0] })
      toast.success(`Intensity: ${value[0]}`)
    } catch {
      toast.error('Failed to set intensity')
    }
  }

  const handleEffectChange = async (value: string) => {
    setSelectedEffect(value)
    try {
      const data = await apiClient.post<{ connected?: boolean; power_on?: boolean }>('/api/dw_leds/effect', { effect_id: parseInt(value) })
      if (data.connected) {
        toast.success('Effect changed')
        if (data.power_on !== undefined) {
          const powerOn = data.power_on
          setDwStatus((prev) => prev ? { ...prev, power_on: powerOn } : null)
        }
      }
    } catch {
      toast.error('Failed to set effect')
    }
  }

  const handlePaletteChange = async (value: string) => {
    setSelectedPalette(value)
    try {
      const data = await apiClient.post<{ connected?: boolean }>('/api/dw_leds/palette', { palette_id: parseInt(value) })
      if (data.connected) {
        toast.success('Palette changed')
      }
    } catch {
      toast.error('Failed to set palette')
    }
  }

  const handleColorChange = (slot: 1 | 2 | 3, value: string) => {
    // Update UI immediately for responsive feedback
    if (slot === 1) setColor1(value)
    else if (slot === 2) setColor2(value)
    else setColor3(value)

    // Clear any pending debounce timer
    if (colorDebounceRef.current) {
      clearTimeout(colorDebounceRef.current)
    }

    // Debounce API call by 300ms to prevent overwhelming the backend
    colorDebounceRef.current = setTimeout(async () => {
      try {
        const hexToRgb = (hex: string) => {
          const r = parseInt(hex.slice(1, 3), 16)
          const g = parseInt(hex.slice(3, 5), 16)
          const b = parseInt(hex.slice(5, 7), 16)
          return [r, g, b]
        }

        const payload: Record<string, number[]> = {}
        payload[`color${slot}`] = hexToRgb(value)

        await apiClient.post('/api/dw_leds/colors', payload)
      } catch (error) {
        console.error('Failed to set color:', error)
      }
    }, 300)
  }

  const saveCurrentEffectSettings = async (type: 'idle' | 'playing') => {
    try {
      const settings = {
        type,
        effect_id: parseInt(selectedEffect) || 0,
        palette_id: parseInt(selectedPalette) || 0,
        speed,
        intensity,
        color1,
        color2,
        color3,
      }

      await apiClient.post('/api/dw_leds/save_effect_settings', settings)
      toast.success(`${type.charAt(0).toUpperCase() + type.slice(1)} effect saved`)
      await fetchEffectSettings()
    } catch {
      toast.error(`Failed to save ${type} effect`)
    }
  }

  const clearEffectSettings = async (type: 'idle' | 'playing') => {
    try {
      await apiClient.post('/api/dw_leds/clear_effect_settings', { type })
      toast.success(`${type.charAt(0).toUpperCase() + type.slice(1)} effect cleared`)
      await fetchEffectSettings()
    } catch {
      toast.error(`Failed to clear ${type} effect`)
    }
  }

  const saveIdleTimeout = async (enabled?: boolean, minutes?: number) => {
    const finalEnabled = enabled !== undefined ? enabled : idleTimeoutEnabled
    const finalMinutes = minutes !== undefined ? minutes : idleTimeoutMinutes
    try {
      await apiClient.post('/api/dw_leds/idle_timeout', { enabled: finalEnabled, minutes: finalMinutes })
      toast.success(`Idle timeout ${finalEnabled ? 'enabled' : 'disabled'}`)
    } catch {
      toast.error('Failed to save idle timeout')
    }
  }

  const handleIdleTimeoutToggle = async (checked: boolean) => {
    setIdleTimeoutEnabled(checked)
    await saveIdleTimeout(checked, idleTimeoutMinutes)
  }

  const formatEffectSettings = (settings: EffectSettings | null) => {
    if (!settings) return 'Not configured'
    const effectName = effects.find((e) => e[0] === settings.effect_id)?.[1] || settings.effect_id
    // Board-provider automation stores only the effect name (the firmware keeps
    // its current palette/speed/colors); other fields come back null.
    if (settings.palette_id == null) return String(effectName)
    const paletteName = palettes.find((p) => p[0] === settings.palette_id)?.[1] || settings.palette_id
    return `${effectName} | ${paletteName} | Speed: ${settings.speed} | Intensity: ${settings.intensity}`
  }

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <span className="material-icons-outlined animate-spin text-4xl text-muted-foreground">
          sync
        </span>
      </div>
    )
  }

  // Not configured state
  if (!ledConfig || ledConfig.provider === 'none') {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6 text-center px-4">
        <div className="p-4 rounded-full bg-muted">
          <span className="material-icons-outlined text-5xl text-muted-foreground">
            lightbulb
          </span>
        </div>
        <div className="space-y-2">
          <h1 className="text-xl sm:text-2xl font-bold font-display">LED Controller Not Configured</h1>
          <p className="text-sm sm:text-base text-muted-foreground max-w-md">
            Configure your LED controller (the table's built-in LEDs or WLED) in the Settings page to control your lights.
          </p>
        </div>
        <Button asChild className="gap-2">
          <Link to="/settings?section=led">
            <span className="material-icons-outlined">settings</span>
            Go to Settings
          </Link>
        </Button>
      </div>
    )
  }

  // Mode selector card (shared between WLED and DW LEDs views)
  const modeSelector = (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg flex items-center gap-2">
          <span className="material-icons-outlined text-muted-foreground">tune</span>
          LED Control Mode
        </CardTitle>
        <CardDescription>
          Choose how Dune Weaver manages LED effects during playback and idle states
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <button
            onClick={() => handleControlModeChange('manual')}
            className={`p-4 rounded-lg border-2 text-left transition-all ${
              controlMode === 'manual'
                ? 'border-primary bg-primary/5'
                : 'border-border hover:border-muted-foreground/30'
            }`}
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="material-icons-outlined text-base">front_hand</span>
              <span className="font-medium text-sm">Manual / Home Assistant</span>
            </div>
            <p className="text-xs text-muted-foreground">
              Effects persist until changed. Still Sands turns off only.
            </p>
          </button>
          <button
            onClick={() => handleControlModeChange('automated')}
            className={`p-4 rounded-lg border-2 text-left transition-all ${
              controlMode === 'automated'
                ? 'border-primary bg-primary/5'
                : 'border-border hover:border-muted-foreground/30'
            }`}
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="material-icons-outlined text-base">smart_toy</span>
              <span className="font-medium text-sm">DW Automated</span>
            </div>
            <p className="text-xs text-muted-foreground">
              Auto-switch effects on play/idle. Still Sands turns off and on.
            </p>
          </button>
        </div>
      </CardContent>
    </Card>
  )

  // WLED iframe view
  if (ledConfig.provider === 'wled' && ledConfig.wled_ip) {
    return (
      <div className="flex flex-col w-full max-w-5xl mx-auto gap-4 py-3 sm:py-6 px-0 sm:px-4">
        {modeSelector}
        <div style={{ height: 'calc(100vh - 380px - env(safe-area-inset-top, 0px) - env(safe-area-inset-bottom, 0px))' }}>
          <iframe
            src={`http://${ledConfig.wled_ip}`}
            className="w-full h-full rounded-lg border border-border"
            title="WLED Control"
          />
        </div>
      </div>
    )
  }

  // LED control panel (board = the table's ring via firmware; dw_leds = legacy host GPIO)
  const isBoard = ledConfig.provider === 'board'
  // Raw firmware effect name -> id (effectNames comes from the board contract)
  const idByName: Record<string, number> = Object.fromEntries(
    effectNames.map(([id, name]) => [name, id])
  )
  const ballId: number | undefined = idByName['ball']
  const isBallEffect = ballId !== undefined && selectedEffect === String(ballId)
  const handleBallToggle = (on: boolean) => {
    if (ballId === undefined) return
    if (on) {
      handleEffectChange(String(ballId))
      return
    }
    const fallback = effects.find(([id]) => id !== ballId)?.[0]
    handleEffectChange(lastNonBallEffect.current || String(fallback ?? 2))
  }
  // Per-effect control visibility, like the mobile app: only board effects are
  // in EFFECT_INPUTS; dw_leds (legacy WLED-style ids) keeps everything visible.
  const selectedEffectName = effectNames.find(([id]) => String(id) === selectedEffect)?.[1]
  const effectInputs =
    isBoard && selectedEffectName
      ? EFFECT_INPUTS[selectedEffectName] ?? { color: true, color2: true, palette: true }
      : { color: true, color2: true, palette: true }
  const showColor1 = isBallEffect || !!effectInputs.color
  // For the ball, the secondary color is the solid background — only relevant
  // when the background style is 'static'.
  const showColor2 = isBallEffect ? ballBg === 'static' : !!effectInputs.color2
  const showPalette = !isBallEffect && !!effectInputs.palette
  // Background sub-effect choices for the ball (firmware effect names, + static/off).
  const ballBgOptions = [
    { value: 'static', label: 'Solid color' },
    { value: 'off', label: 'Off (black)' },
    ...effectNames
      .filter(([, name]) => !['ball', 'off', 'static'].includes(name))
      .map(([id, name]) => ({
        value: name,
        label: effects.find(([eid]) => eid === id)?.[1] || name,
      }))
      .sort((a, b) => a.label.localeCompare(b.label)),
  ]
  const powerOn = !!dwStatus?.power_on
  return (
    <div className="flex flex-col w-full max-w-4xl mx-auto gap-6 py-3 sm:py-6 px-0 sm:px-4">
      {/* Page Header */}
      <div className="space-y-0.5 sm:space-y-1 pl-1">
        <h1 className="text-xl font-semibold tracking-tight font-display">LED Control</h1>
        <p className="text-xs text-muted-foreground">
          {isBoard ? "Table's built-in LED ring, controlled by the firmware" : 'DW LEDs - GPIO controlled LED strip'}
        </p>
      </div>

      <Separator />

      {!isBoard && modeSelector}

      {/* Ring card: power, brightness and colors, previewed on a live LED ring */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col sm:flex-row items-center gap-8">
            {/* Live preview of the selected effect (firmware engine port),
                with the power button in the ring's center */}
            <div className="relative h-40 w-40 shrink-0">
              <LedRingPreview
                className="absolute inset-0 h-full w-full"
                effectId={isBoard && selectedEffect !== '' ? parseInt(selectedEffect) : 9}
                paletteId={parseInt(selectedPalette) || 0}
                color1={color1}
                color2={color2}
                brightness={brightness}
                speed={speed}
                powerOn={powerOn}
                ball={{
                  size: ballSize,
                  direction: ballDirection,
                  align: ballAlign,
                  fgbright: ballFgBright,
                  bgbright: ballBgBright,
                  bgEffectId: idByName[ballBg] ?? 1,
                }}
              />
              <button
                onClick={handlePowerToggle}
                aria-pressed={powerOn}
                aria-label={powerOn ? 'Turn LEDs off' : 'Turn LEDs on'}
                className="absolute inset-0 m-auto flex h-20 w-20 items-center justify-center rounded-full border bg-card shadow-md transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card"
              >
                <span
                  className={`material-icons text-3xl transition-colors ${
                    powerOn ? 'text-success' : 'text-muted-foreground'
                  }`}
                >
                  power_settings_new
                </span>
              </button>
            </div>

            {/* Status, brightness and colors */}
            <div className="w-full flex-1 space-y-5">
              <div className="flex items-center justify-between">
                <div className={`flex items-center gap-2 text-sm ${dwStatus?.connected ? 'text-success' : 'text-destructive'}`}>
                  <span className="material-icons-outlined text-base">
                    {dwStatus?.connected ? 'check_circle' : 'error'}
                  </span>
                  {dwStatus?.connected
                    ? (isBoard ? 'Table LEDs connected' : `${dwStatus.num_leds} LEDs on GPIO ${dwStatus.gpio_pin}`)
                    : 'Not connected'}
                </div>
                <span
                  className={`text-xs font-semibold uppercase tracking-wider font-display ${
                    powerOn ? 'text-success' : 'text-muted-foreground'
                  }`}
                >
                  {powerOn ? 'On' : 'Off'}
                </span>
              </div>

              <div className="space-y-2">
                <div className="flex justify-between items-center">
                  <Label>
                    <span className="material-icons-outlined text-sm mr-2 align-[-6px] text-muted-foreground">brightness_6</span>
                    Brightness
                  </Label>
                  <span className="text-sm font-medium">{brightness}%</span>
                </div>
                <Slider
                  value={[brightness]}
                  onValueChange={handleBrightnessChange}
                  onValueCommit={handleBrightnessCommit}
                  max={100}
                  step={1}
                />
              </div>

            </div>
          </div>
        </CardContent>
      </Card>

      {/* Effects Card */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center gap-2">
            <span className="material-icons-outlined text-muted-foreground">auto_awesome</span>
            Effects & Palettes
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Effect & Palette Selects */}
          <div className={`grid grid-cols-1 gap-4 ${showPalette ? 'sm:grid-cols-2' : ''}`}>
            <div className="space-y-2">
              <Label>Effect</Label>
              {/* Disabled while the ball tracker owns the ring; 'Ball' is only
                  selectable via its toggle below, not from this list */}
              <Select value={selectedEffect} onValueChange={handleEffectChange} disabled={isBallEffect}>
                <SelectTrigger>
                  <SelectValue placeholder="Select effect..." />
                </SelectTrigger>
                <SelectContent>
                  {effects
                    .filter(([id]) => id !== ballId || isBallEffect)
                    .map(([id, name]) => (
                      <SelectItem key={id} value={String(id)}>
                        {name}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
              {isBallEffect && (
                <p className="text-xs text-muted-foreground">
                  Ball tracker is on — turn it off to pick an effect.
                </p>
              )}
            </div>
            {/* Only effects that color from a palette get the palette picker */}
            {showPalette && (
              <div className="space-y-2">
                <Label>Palette</Label>
                <Select value={selectedPalette} onValueChange={handlePaletteChange}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select palette..." />
                  </SelectTrigger>
                  <SelectContent>
                    {palettes.map(([id, name]) => (
                      <SelectItem key={id} value={String(id)}>
                        {name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          {/* Only the swatches the selected effect actually uses (app parity) */}
          {(showColor1 || showColor2) && (
            <div>
              <Label>
                <span className="material-icons-outlined text-sm mr-2 align-[-6px] text-muted-foreground">palette</span>
                {showColor1 && !showColor2 && !isBallEffect ? 'Color' : 'Colors'}
              </Label>
              <div className="flex items-start gap-5">
                {showColor1 && (
                  <div className="flex flex-col items-center gap-1.5">
                    <ColorPicker
                      value={color1}
                      onChange={(color) => handleColorChange(1, color)}
                    />
                    <span className="text-xs text-muted-foreground">
                      {isBallEffect ? 'Blob' : showColor2 ? 'Primary' : 'Color'}
                    </span>
                  </div>
                )}
                {showColor2 && (
                  <div className="flex flex-col items-center gap-1.5">
                    <ColorPicker
                      value={color2}
                      onChange={(color) => handleColorChange(2, color)}
                    />
                    <span className="text-xs text-muted-foreground">{isBallEffect ? 'Background' : 'Secondary'}</span>
                  </div>
                )}
                {/* The firmware only has two colors (Color/Color2) — dw_leds only */}
                {!isBoard && (
                  <div className="flex flex-col items-center gap-1.5">
                    <ColorPicker
                      value={color3}
                      onChange={(color) => handleColorChange(3, color)}
                    />
                    <span className="text-xs text-muted-foreground">Accent</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Speed full-width for the board; Speed + Intensity side by side for dw_leds */}
          <div className={`grid grid-cols-1 gap-x-8 gap-y-6 ${isBoard ? '' : 'sm:grid-cols-2'}`}>
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <Label>
                  <span className="material-icons-outlined text-sm mr-2 align-[-6px] text-muted-foreground">speed</span>
                  Speed
                </Label>
                <Input
                  type="text"
                  inputMode="numeric"
                  value={speedInput}
                  onChange={(e) => {
                    const val = e.target.value.replace(/[^0-9]/g, '')
                    setSpeedInput(val)
                  }}
                  onBlur={() => {
                    const num = Math.min(255, Math.max(0, parseInt(speedInput) || 0))
                    setSpeed(num)
                    setSpeedInput(String(num))
                    handleSpeedCommit([num])
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      const num = Math.min(255, Math.max(0, parseInt(speedInput) || 0))
                      setSpeed(num)
                      setSpeedInput(String(num))
                      handleSpeedCommit([num])
                    }
                  }}
                  className="w-16 h-7 text-center text-sm font-medium px-2"
                />
              </div>
              <Slider
                value={[speed]}
                onValueChange={handleSpeedChange}
                onValueCommit={handleSpeedCommit}
                max={255}
                step={1}
              />
            </div>
            {/* The firmware has no intensity control — dw_leds only */}
            {!isBoard && (
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <Label>
                  <span className="material-icons-outlined text-sm mr-2 align-[-6px] text-muted-foreground">tungsten</span>
                  Intensity
                </Label>
                <Input
                  type="text"
                  inputMode="numeric"
                  value={intensityInput}
                  onChange={(e) => {
                    const val = e.target.value.replace(/[^0-9]/g, '')
                    setIntensityInput(val)
                  }}
                  onBlur={() => {
                    const num = Math.min(255, Math.max(0, parseInt(intensityInput) || 0))
                    setIntensity(num)
                    setIntensityInput(String(num))
                    handleIntensityCommit([num])
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      const num = Math.min(255, Math.max(0, parseInt(intensityInput) || 0))
                      setIntensity(num)
                      setIntensityInput(String(num))
                      handleIntensityCommit([num])
                    }
                  }}
                  className="w-16 h-7 text-center text-sm font-medium px-2"
                />
              </div>
              <Slider
                value={[intensity]}
                onValueChange={handleIntensityChange}
                onValueCommit={handleIntensityCommit}
                max={255}
                step={1}
              />
            </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Auto Turn Off - host-side idle timeout, dw_leds only (the board's
          own Still Sands / IdleEffect cover this for built-in LEDs) */}
      {!isBoard && controlMode === 'automated' && (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center gap-2">
            <span className="material-icons-outlined text-muted-foreground">schedule</span>
            Auto Turn Off
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Enable timeout</span>
            <Switch
              checked={idleTimeoutEnabled}
              onCheckedChange={handleIdleTimeoutToggle}
            />
          </div>
          {idleTimeoutEnabled && (
            <div className="flex items-center gap-2">
              <Input
                type="text"
                inputMode="numeric"
                value={idleTimeoutInput}
                onChange={(e) => {
                  const val = e.target.value.replace(/[^0-9]/g, '')
                  setIdleTimeoutInput(val)
                }}
                onBlur={() => {
                  const num = Math.min(1440, Math.max(1, parseInt(idleTimeoutInput) || 30))
                  setIdleTimeoutMinutes(num)
                  setIdleTimeoutInput(String(num))
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    const num = Math.min(1440, Math.max(1, parseInt(idleTimeoutInput) || 30))
                    setIdleTimeoutMinutes(num)
                    setIdleTimeoutInput(String(num))
                    saveIdleTimeout(idleTimeoutEnabled, num)
                  }
                }}
                className="w-20"
              />
              <span className="text-sm text-muted-foreground flex-1">minutes</span>
              <Button size="sm" onClick={() => saveIdleTimeout()}>
                Save
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
      )}

      {/* Ball Tracker - firmware-native effect that follows the sand ball.
          Its own toggle (not an entry in the Effect list); when on it takes
          over the ring and the Effect select is disabled. */}
      {isBoard && ballId !== undefined && (
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1.5">
              <CardTitle className="text-lg flex items-center gap-2">
                <span className="material-icons-outlined text-muted-foreground">sports_baseball</span>
                Ball Tracker
              </CardTitle>
              <CardDescription>
                A glowing dot that follows the sand ball around the ring. While on, the Colors above set the blob and background.
              </CardDescription>
            </div>
            <Switch
              checked={isBallEffect}
              onCheckedChange={handleBallToggle}
              aria-label="Ball tracker"
            />
          </div>
        </CardHeader>
        {isBallEffect && (
        <CardContent>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-8 gap-y-6">
            {/* Blob column */}
            <div className="space-y-4">
              <p className="text-sm font-medium flex items-center gap-2">
                <span className="material-icons-outlined text-base text-muted-foreground">circle</span>
                Blob
                <span className="text-xs font-normal text-muted-foreground">the dot that tracks the ball</span>
              </p>
              <div className="p-4 rounded-lg border space-y-3">
                <div className="flex justify-between items-center">
                  <Label>Brightness</Label>
                  <span className="text-sm font-medium">{ballFgBright}</span>
                </div>
                <Slider
                  value={[ballFgBright]}
                  onValueChange={(v) => setBallFgBright(v[0])}
                  onValueCommit={(v) => { setBallFgBright(v[0]); sendBall({ fgbright: v[0] }) }}
                  max={255}
                  step={1}
                />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Direction</Label>
                  <Select
                    value={ballDirection}
                    onValueChange={(v) => { const d = v as 'cw' | 'ccw'; setBallDirection(d); sendBall({ direction: d }) }}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="cw">Clockwise</SelectItem>
                      <SelectItem value="ccw">Counter-clockwise</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="p-4 rounded-lg border space-y-3">
                  <div className="flex justify-between items-center">
                    <Label>Glow size</Label>
                    <span className="text-sm font-medium">{ballSize}</span>
                  </div>
                  <Slider
                    value={[ballSize]}
                    onValueChange={(v) => setBallSize(v[0])}
                    onValueCommit={(v) => { setBallSize(v[0]); sendBall({ size: v[0] }) }}
                    min={1}
                    max={30}
                    step={1}
                  />
                </div>
              </div>
              <div className="p-4 rounded-lg border space-y-3">
                <div className="flex justify-between items-center">
                  <Label>Alignment (°)</Label>
                  <span className="text-sm font-medium">{ballAlign}</span>
                </div>
                <Slider
                  value={[ballAlign]}
                  onValueChange={(v) => setBallAlign(v[0])}
                  onValueCommit={(v) => { setBallAlign(v[0]); sendBall({ align: v[0] }) }}
                  max={359}
                  step={1}
                />
                <p className="text-xs text-muted-foreground">Rotate the blob so it sits on the ball.</p>
              </div>
            </div>

            {/* Background column */}
            <div className="space-y-4 lg:border-l lg:pl-8">
              <p className="text-sm font-medium flex items-center gap-2">
                <span className="material-icons-outlined text-base text-muted-foreground">gradient</span>
                Background
                <span className="text-xs font-normal text-muted-foreground">behind the blob</span>
              </p>
              <div className="space-y-2">
                <Label>Style</Label>
                <Select value={ballBg} onValueChange={(v) => { setBallBg(v); sendBall({ bg: v }) }}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {ballBgOptions.map((o) => (
                      <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {ballBg === 'static'
                    ? 'Solid fill using the Background color from the Colors panel above.'
                    : ballBg === 'off'
                      ? 'The ring stays dark behind the blob.'
                      : 'Runs another effect behind the blob.'}
                </p>
              </div>
              {ballBg !== 'off' && (
                <div className="p-4 rounded-lg border space-y-3">
                  <div className="flex justify-between items-center">
                    <Label>Background brightness</Label>
                    <span className="text-sm font-medium">{ballBgBright}</span>
                  </div>
                  <Slider
                    value={[ballBgBright]}
                    onValueChange={(v) => setBallBgBright(v[0])}
                    onValueCommit={(v) => { setBallBgBright(v[0]); sendBall({ bgbright: v[0] }) }}
                    max={255}
                    step={1}
                  />
                </div>
              )}
            </div>
          </div>
        </CardContent>
        )}
      </Card>
      )}

      {/* Automation Settings - Full Width - hidden in manual mode.
          For board LEDs the switching happens on the table itself
          ($LED/RunEffect / $LED/IdleEffect), so it's always available. */}
      {(isBoard || controlMode === 'automated') && (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center gap-2">
            <span className="material-icons-outlined text-muted-foreground">smart_toy</span>
            Effect Automation
          </CardTitle>
          <CardDescription>
            {isBoard
              ? 'The table switches to these effects by itself while drawing and at rest'
              : 'Save current settings to automatically apply when table state changes'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Playing Effect */}
            <div className="p-4 rounded-lg border space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="material-icons text-live">play_circle</span>
                  <span className="font-medium">While Playing</span>
                </div>
              </div>
              {playingEffect ? (
                <div className="text-xs p-2 bg-muted/50 rounded border min-h-[40px]">
                  {formatEffectSettings(playingEffect)}
                </div>
              ) : (
                <div className="text-xs text-muted-foreground italic p-2 rounded border border-dashed min-h-[40px]">
                  Not configured — save the current effect to use it here
                </div>
              )}
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={() => saveCurrentEffectSettings('playing')}
                  className="flex-1 gap-1"
                >
                  <span className="material-icons text-sm">save</span>
                  Save Current
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => clearEffectSettings('playing')}
                >
                  Clear
                </Button>
              </div>
            </div>

            {/* Idle Effect */}
            <div className="p-4 rounded-lg border space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="material-icons text-primary">bedtime</span>
                  <span className="font-medium">When Idle</span>
                </div>
              </div>
              {idleEffect ? (
                <div className="text-xs p-2 bg-muted/50 rounded border min-h-[40px]">
                  {formatEffectSettings(idleEffect)}
                </div>
              ) : (
                <div className="text-xs text-muted-foreground italic p-2 rounded border border-dashed min-h-[40px]">
                  Not configured — save the current effect to use it here
                </div>
              )}
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={() => saveCurrentEffectSettings('idle')}
                  className="flex-1 gap-1"
                >
                  <span className="material-icons text-sm">save</span>
                  Save Current
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => clearEffectSettings('idle')}
                >
                  Clear
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
      )}
    </div>
  )
}
