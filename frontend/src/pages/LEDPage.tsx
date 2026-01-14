import { useState, useEffect, useCallback } from 'react'
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

// Types
interface LedConfig {
  provider: 'none' | 'wled' | 'dw_leds'
  wled_ip?: string
  num_leds?: number
  gpio_pin?: number
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

export function LEDPage() {
  const [ledConfig, setLedConfig] = useState<LedConfig | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  // DW LEDs state
  const [dwStatus, setDwStatus] = useState<DWLedsStatus | null>(null)
  const [effects, setEffects] = useState<[number, string][]>([])
  const [palettes, setPalettes] = useState<[number, string][]>([])
  const [brightness, setBrightness] = useState(35)
  const [speed, setSpeed] = useState(128)
  const [intensity, setIntensity] = useState(128)
  const [selectedEffect, setSelectedEffect] = useState('')
  const [selectedPalette, setSelectedPalette] = useState('')
  const [color1, setColor1] = useState('#ff0000')
  const [color2, setColor2] = useState('#000000')
  const [color3, setColor3] = useState('#0000ff')

  // Effect automation state
  const [idleEffect, setIdleEffect] = useState<EffectSettings | null>(null)
  const [playingEffect, setPlayingEffect] = useState<EffectSettings | null>(null)
  const [idleTimeoutEnabled, setIdleTimeoutEnabled] = useState(false)
  const [idleTimeoutMinutes, setIdleTimeoutMinutes] = useState(30)

  // Fetch LED configuration
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const data = await apiClient.get<{ provider?: string; wled_ip?: string; dw_led_num_leds?: number; dw_led_gpio_pin?: number }>('/get_led_config')
        // Map backend response fields to our interface
        setLedConfig({
          provider: (data.provider as LedConfig['provider']) || 'none',
          wled_ip: data.wled_ip,
          num_leds: data.dw_led_num_leds,
          gpio_pin: data.dw_led_gpio_pin,
        })
      } catch (error) {
        console.error('Error fetching LED config:', error)
      } finally {
        setIsLoading(false)
      }
    }
    fetchConfig()
  }, [])

  // Initialize DW LEDs when provider is dw_leds
  useEffect(() => {
    if (ledConfig?.provider === 'dw_leds') {
      fetchDWLedsStatus()
      fetchEffectsAndPalettes()
      fetchEffectSettings()
      fetchIdleTimeout()
    }
  }, [ledConfig])

  const fetchDWLedsStatus = async () => {
    try {
      const data = await apiClient.get<DWLedsStatus>('/api/dw_leds/status')
      setDwStatus(data)
      if (data.connected) {
        setBrightness(data.brightness || 35)
        setSpeed(data.speed || 128)
        setIntensity(data.intensity || 128)
        setSelectedEffect(String(data.current_effect || 0))
        setSelectedPalette(String(data.current_palette || 0))
        if (data.colors) {
          setColor1(data.colors[0] || '#ff0000')
          setColor2(data.colors[1] || '#000000')
          setColor3(data.colors[2] || '#0000ff')
        }
      }
    } catch (error) {
      console.error('Error fetching DW LEDs status:', error)
    }
  }

  const fetchEffectsAndPalettes = async () => {
    try {
      const [effectsData, palettesData] = await Promise.all([
        apiClient.get<{ effects?: [number, string][] }>('/api/dw_leds/effects'),
        apiClient.get<{ palettes?: [number, string][] }>('/api/dw_leds/palettes'),
      ])

      if (effectsData.effects) {
        const sorted = [...effectsData.effects].sort((a, b) => a[1].localeCompare(b[1]))
        setEffects(sorted)
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

  const fetchIdleTimeout = async () => {
    try {
      const data = await apiClient.get<{ enabled?: boolean; minutes?: number }>('/api/dw_leds/idle_timeout')
      setIdleTimeoutEnabled(data.enabled || false)
      setIdleTimeoutMinutes(data.minutes || 30)
    } catch (error) {
      console.error('Error fetching idle timeout:', error)
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

  const handleColorChange = async (slot: 1 | 2 | 3, value: string) => {
    if (slot === 1) setColor1(value)
    else if (slot === 2) setColor2(value)
    else setColor3(value)

    // Debounce color changes
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
          <h1 className="text-xl sm:text-2xl font-bold">LED Controller Not Configured</h1>
          <p className="text-sm sm:text-base text-muted-foreground max-w-md">
            Configure your LED controller (WLED or DW LEDs) in the Settings page to control your lights.
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

  // WLED iframe view
  if (ledConfig.provider === 'wled' && ledConfig.wled_ip) {
    return (
      <div className="flex flex-col w-full h-[calc(100vh-180px)] py-4">
        <iframe
          src={`http://${ledConfig.wled_ip}`}
          className="w-full h-full rounded-lg border border-border"
          title="WLED Control"
        />
      </div>
    )
  }

  // DW LEDs control panel
  return (
    <div className="flex flex-col w-full max-w-5xl mx-auto gap-6 py-6 px-4">
      {/* Page Header */}
      <div className="space-y-0.5 sm:space-y-1">
        <h1 className="text-xl sm:text-3xl font-bold tracking-tight">LED Control</h1>
        <p className="text-xs sm:text-base text-muted-foreground">DW LEDs - GPIO controlled LED strip</p>
      </div>

      <Separator />

      {/* Main Control Grid - 2 columns on large screens */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column - Primary Controls */}
        <div className="lg:col-span-2 space-y-6">
          {/* Power & Status Card */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex flex-col sm:flex-row items-center gap-6">
                {/* Power Button - Large and prominent */}
                <div className="flex flex-col items-center gap-3">
                  <button
                    onClick={handlePowerToggle}
                    className={`w-24 h-24 rounded-full flex items-center justify-center transition-all shadow-lg ${
                      dwStatus?.power_on
                        ? 'bg-green-500 hover:bg-green-600 shadow-green-500/30'
                        : 'bg-muted hover:bg-muted/80'
                    }`}
                  >
                    <span className={`material-icons text-4xl ${dwStatus?.power_on ? 'text-white' : 'text-muted-foreground'}`}>
                      power_settings_new
                    </span>
                  </button>
                  <span className={`text-sm font-medium ${dwStatus?.power_on ? 'text-green-600' : 'text-muted-foreground'}`}>
                    {dwStatus?.power_on ? 'ON' : 'OFF'}
                  </span>
                </div>

                {/* Status & Brightness */}
                <div className="flex-1 w-full space-y-4">
                  {/* Connection Status */}
                  <div className={`flex items-center gap-2 text-sm ${dwStatus?.connected ? 'text-green-600' : 'text-destructive'}`}>
                    <span className="material-icons-outlined text-base">
                      {dwStatus?.connected ? 'check_circle' : 'error'}
                    </span>
                    {dwStatus?.connected
                      ? `${dwStatus.num_leds} LEDs on GPIO ${dwStatus.gpio_pin}`
                      : 'Not connected'}
                  </div>

                  {/* Brightness Slider */}
                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <Label className="flex items-center gap-2">
                        <span className="material-icons-outlined text-base text-muted-foreground">brightness_6</span>
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
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Effect</Label>
                  <Select value={selectedEffect} onValueChange={handleEffectChange}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select effect..." />
                    </SelectTrigger>
                    <SelectContent>
                      {effects.map(([id, name]) => (
                        <SelectItem key={id} value={String(id)}>
                          {name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
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
              </div>

              {/* Speed and Intensity in styled boxes */}
              <div className="grid grid-cols-2 gap-4">
                <div className="p-4 bg-muted/50 rounded-lg space-y-3">
                  <div className="flex justify-between items-center">
                    <Label className="flex items-center gap-2">
                      <span className="material-icons-outlined text-base text-muted-foreground">speed</span>
                      Speed
                    </Label>
                    <span className="text-sm font-medium">{speed}</span>
                  </div>
                  <Slider
                    value={[speed]}
                    onValueChange={handleSpeedChange}
                    onValueCommit={handleSpeedCommit}
                    max={255}
                    step={1}
                  />
                </div>
                <div className="p-4 bg-muted/50 rounded-lg space-y-3">
                  <div className="flex justify-between items-center">
                    <Label className="flex items-center gap-2">
                      <span className="material-icons-outlined text-base text-muted-foreground">tungsten</span>
                      Intensity
                    </Label>
                    <span className="text-sm font-medium">{intensity}</span>
                  </div>
                  <Slider
                    value={[intensity]}
                    onValueChange={handleIntensityChange}
                    onValueCommit={handleIntensityCommit}
                    max={255}
                    step={1}
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right Column - Colors & Quick Settings */}
        <div className="flex flex-col gap-6">
          {/* Colors Card */}
          <Card className="flex-1 flex flex-col">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center gap-2">
                <span className="material-icons-outlined text-muted-foreground">palette</span>
                Colors
              </CardTitle>
            </CardHeader>
            <CardContent className="flex-1 flex items-center justify-center">
              <div className="flex justify-around w-full">
                <div className="flex flex-col items-center gap-2">
                  <ColorPicker
                    value={color1}
                    onChange={(color) => handleColorChange(1, color)}
                  />
                  <span className="text-xs text-muted-foreground">Primary</span>
                </div>
                <div className="flex flex-col items-center gap-2">
                  <ColorPicker
                    value={color2}
                    onChange={(color) => handleColorChange(2, color)}
                  />
                  <span className="text-xs text-muted-foreground">Secondary</span>
                </div>
                <div className="flex flex-col items-center gap-2">
                  <ColorPicker
                    value={color3}
                    onChange={(color) => handleColorChange(3, color)}
                  />
                  <span className="text-xs text-muted-foreground">Accent</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Auto Turn Off */}
          <Card className="flex-1 flex flex-col">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center gap-2">
                <span className="material-icons-outlined text-muted-foreground">schedule</span>
                Auto Turn Off
              </CardTitle>
            </CardHeader>
            <CardContent className="flex-1 flex flex-col justify-center space-y-4">
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
                    type="number"
                    value={idleTimeoutMinutes}
                    onChange={(e) => setIdleTimeoutMinutes(parseInt(e.target.value) || 30)}
                    min={1}
                    max={1440}
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
        </div>
      </div>

      {/* Automation Settings - Full Width */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center gap-2">
            <span className="material-icons-outlined text-muted-foreground">smart_toy</span>
            Effect Automation
          </CardTitle>
          <CardDescription>
            Save current settings to automatically apply when table state changes
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Playing Effect */}
            <div className="p-4 bg-muted/50 rounded-lg space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="material-icons text-green-600">play_circle</span>
                  <span className="font-medium">While Playing</span>
                </div>
              </div>
              <div className="text-xs text-muted-foreground p-2 bg-background rounded border min-h-[40px]">
                {formatEffectSettings(playingEffect)}
              </div>
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
                  variant="outline"
                  onClick={() => clearEffectSettings('playing')}
                >
                  Clear
                </Button>
              </div>
            </div>

            {/* Idle Effect */}
            <div className="p-4 bg-muted/50 rounded-lg space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="material-icons text-blue-600">bedtime</span>
                  <span className="font-medium">When Idle</span>
                </div>
              </div>
              <div className="text-xs text-muted-foreground p-2 bg-background rounded border min-h-[40px]">
                {formatEffectSettings(idleEffect)}
              </div>
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
                  variant="outline"
                  onClick={() => clearEffectSettings('idle')}
                >
                  Clear
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
