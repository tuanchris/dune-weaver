import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'

// Types
interface SerialPort {
  port: string
  description: string
}

interface Settings {
  app_name?: string
  custom_logo?: string
  preferred_port?: string
  table_type_override?: string
  homing_mode?: number
  angular_offset?: number
  auto_home_enabled?: boolean
  auto_home_after_patterns?: number
  clear_pattern_speed?: number
  custom_clear_from_in?: string
  custom_clear_from_out?: string
}

interface LedConfig {
  provider: 'none' | 'wled' | 'dw_leds'
  wled_ip?: string
  num_leds?: number
  gpio_pin?: number
  pixel_order?: string
}

interface MqttConfig {
  enabled: boolean
  broker?: string
  port?: number
  username?: string
  password?: string
  device_name?: string
  device_id?: string
  client_id?: string
  discovery_prefix?: string
}

export function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const sectionParam = searchParams.get('section')

  // Connection state
  const [ports, setPorts] = useState<SerialPort[]>([])
  const [selectedPort, setSelectedPort] = useState('')
  const [isConnected, setIsConnected] = useState(false)
  const [connectionStatus, setConnectionStatus] = useState('Disconnected')

  // Settings state
  const [settings, setSettings] = useState<Settings>({})
  const [ledConfig, setLedConfig] = useState<LedConfig>({ provider: 'none' })
  const [mqttConfig, setMqttConfig] = useState<MqttConfig>({ enabled: false })

  // UI state
  const [isLoading, setIsLoading] = useState<string | null>(null)

  // Accordion state - controlled by URL params
  const [openSections, setOpenSections] = useState<string[]>(() => {
    if (sectionParam) return [sectionParam]
    return ['connection']
  })

  // Track which sections have been loaded (for lazy loading)
  const [loadedSections, setLoadedSections] = useState<Set<string>>(new Set())

  // Auto-play state
  const [autoPlayEnabled, setAutoPlayEnabled] = useState(false)
  const [playlists, setPlaylists] = useState<string[]>([])

  // Still Sands state
  const [stillSandsEnabled, setStillSandsEnabled] = useState(false)

  // Scroll to section and clear URL param after navigation
  useEffect(() => {
    if (sectionParam) {
      // Scroll to the section after a short delay to allow render
      setTimeout(() => {
        const element = document.getElementById(`section-${sectionParam}`)
        if (element) {
          element.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }
        // Clear the search param from URL
        setSearchParams({}, { replace: true })
      }, 100)
    }
  }, [sectionParam, setSearchParams])

  // Load section data when expanded (lazy loading)
  const loadSectionData = async (section: string) => {
    if (loadedSections.has(section)) return

    setLoadedSections((prev) => new Set(prev).add(section))

    switch (section) {
      case 'connection':
        await fetchPorts()
        break
      case 'application':
      case 'mqtt':
      case 'autoplay':
      case 'stillsands':
        // These all share settings data
        if (!loadedSections.has('_settings')) {
          setLoadedSections((prev) => new Set(prev).add('_settings'))
          await fetchSettings()
        }
        if (section === 'autoplay' && !loadedSections.has('_playlists')) {
          setLoadedSections((prev) => new Set(prev).add('_playlists'))
          await fetchPlaylists()
        }
        break
      case 'led':
        await fetchLedConfig()
        break
    }
  }

  // Handle accordion open/close and trigger data loading
  const handleAccordionChange = (values: string[]) => {
    // Find newly opened section
    const newlyOpened = values.find((v) => !openSections.includes(v))

    setOpenSections(values)

    // Load data for newly opened sections
    values.forEach((section) => {
      if (!loadedSections.has(section)) {
        loadSectionData(section)
      }
    })

    // Scroll newly opened section into view
    if (newlyOpened) {
      setTimeout(() => {
        const element = document.getElementById(`section-${newlyOpened}`)
        if (element) {
          element.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }
      }, 100)
    }
  }

  // Load initial section data
  useEffect(() => {
    openSections.forEach((section) => {
      loadSectionData(section)
    })
  }, [])

  const fetchPorts = async () => {
    try {
      const response = await fetch('/serial_status')
      const data = await response.json()
      console.log('Serial status response:', data)
      setPorts(data.available_ports || [])
      setIsConnected(data.connected || false)
      setConnectionStatus(data.connected ? 'Connected' : 'Disconnected')
      if (data.current_port) {
        setSelectedPort(data.current_port)
      }
    } catch (error) {
      console.error('Error fetching ports:', error)
    }
  }

  // Always fetch ports on mount since connection is the default section
  useEffect(() => {
    fetchPorts()
  }, [])

  const fetchSettings = async () => {
    try {
      const response = await fetch('/api/settings')
      const data = await response.json()
      // Map the nested API response to our flat Settings interface
      setSettings({
        app_name: data.app?.name,
        custom_logo: data.app?.custom_logo,
        preferred_port: data.connection?.preferred_port,
        clear_pattern_speed: data.patterns?.clear_pattern_speed,
        custom_clear_from_in: data.patterns?.custom_clear_from_in,
        custom_clear_from_out: data.patterns?.custom_clear_from_out,
      })
      // Also set auto-play and still sands from the same response
      if (data.auto_play) {
        setAutoPlayEnabled(data.auto_play.enabled || false)
      }
      if (data.scheduled_pause) {
        setStillSandsEnabled(data.scheduled_pause.enabled || false)
      }
      // Set MQTT config from the same response
      if (data.mqtt) {
        setMqttConfig({
          enabled: data.mqtt.enabled || false,
          broker: data.mqtt.broker,
          port: data.mqtt.port,
          username: data.mqtt.username,
          device_name: data.mqtt.device_name,
          device_id: data.mqtt.device_id,
          client_id: data.mqtt.client_id,
          discovery_prefix: data.mqtt.discovery_prefix,
        })
      }
    } catch (error) {
      console.error('Error fetching settings:', error)
    }
  }

  const fetchLedConfig = async () => {
    try {
      const response = await fetch('/get_led_config')
      const data = await response.json()
      setLedConfig({
        provider: data.provider || 'none',
        wled_ip: data.wled_ip,
        num_leds: data.dw_led_num_leds,
        gpio_pin: data.dw_led_gpio_pin,
        pixel_order: data.dw_led_pixel_order,
      })
    } catch (error) {
      console.error('Error fetching LED config:', error)
    }
  }

  const fetchPlaylists = async () => {
    try {
      const response = await fetch('/list_all_playlists')
      const data = await response.json()
      setPlaylists(data.playlists || [])
    } catch (error) {
      console.error('Error fetching playlists:', error)
    }
  }

  const handleConnect = async () => {
    if (!selectedPort) {
      toast.error('Please select a port')
      return
    }
    setIsLoading('connect')
    try {
      const response = await fetch('/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ port: selectedPort }),
      })
      const data = await response.json()
      if (data.success) {
        setIsConnected(true)
        setConnectionStatus(`Connected to ${selectedPort}`)
        toast.success('Connected successfully')
      } else {
        throw new Error(data.message || 'Connection failed')
      }
    } catch (error) {
      toast.error('Failed to connect')
    } finally {
      setIsLoading(null)
    }
  }

  const handleDisconnect = async () => {
    setIsLoading('disconnect')
    try {
      const response = await fetch('/disconnect', { method: 'POST' })
      const data = await response.json()
      if (data.success) {
        setIsConnected(false)
        setConnectionStatus('Disconnected')
        toast.success('Disconnected')
      }
    } catch (error) {
      toast.error('Failed to disconnect')
    } finally {
      setIsLoading(null)
    }
  }

  const handleSaveAppName = async () => {
    setIsLoading('appName')
    try {
      const response = await fetch('/api/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ app: { name: settings.app_name } }),
      })
      if (response.ok) {
        toast.success('App name saved. Refresh to see changes.')
      }
    } catch (error) {
      toast.error('Failed to save app name')
    } finally {
      setIsLoading(null)
    }
  }

  // Update favicon links in the document head and notify Layout to refresh
  const updateBranding = (customLogo: string | null) => {
    const timestamp = Date.now() // Cache buster

    // Update favicon links
    const faviconIco = document.getElementById('favicon-ico') as HTMLLinkElement
    const appleTouchIcon = document.getElementById('apple-touch-icon') as HTMLLinkElement

    if (customLogo) {
      if (faviconIco) faviconIco.href = `/static/custom/favicon.ico?v=${timestamp}`
      if (appleTouchIcon) appleTouchIcon.href = `/static/custom/${customLogo}?v=${timestamp}`
    } else {
      if (faviconIco) faviconIco.href = `/static/favicon.ico?v=${timestamp}`
      if (appleTouchIcon) appleTouchIcon.href = `/static/apple-touch-icon.png?v=${timestamp}`
    }

    // Dispatch event for Layout to update header logo
    window.dispatchEvent(new CustomEvent('branding-updated'))
  }

  const handleLogoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    setIsLoading('logo')
    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch('/api/upload-logo', {
        method: 'POST',
        body: formData,
      })

      if (response.ok) {
        const data = await response.json()
        setSettings({ ...settings, custom_logo: data.filename })
        updateBranding(data.filename)
        toast.success('Logo uploaded!')
      } else {
        const data = await response.json()
        throw new Error(data.detail || 'Upload failed')
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to upload logo')
    } finally {
      setIsLoading(null)
      // Reset the input
      e.target.value = ''
    }
  }

  const handleDeleteLogo = async () => {
    if (!confirm('Remove custom logo and revert to default?')) return

    setIsLoading('logo')
    try {
      const response = await fetch('/api/custom-logo', { method: 'DELETE' })
      if (response.ok) {
        setSettings({ ...settings, custom_logo: undefined })
        updateBranding(null)
        toast.success('Logo removed!')
      }
    } catch (error) {
      toast.error('Failed to remove logo')
    } finally {
      setIsLoading(null)
    }
  }

  const handleSaveLedConfig = async () => {
    setIsLoading('led')
    try {
      // Use the /set_led_config endpoint (deprecated but still works)
      const response = await fetch('/set_led_config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: ledConfig.provider,
          ip_address: ledConfig.wled_ip,
          num_leds: ledConfig.num_leds,
          gpio_pin: ledConfig.gpio_pin,
          pixel_order: ledConfig.pixel_order,
        }),
      })
      if (response.ok) {
        toast.success('LED configuration saved')
      } else {
        const data = await response.json()
        throw new Error(data.detail || 'Failed to save LED config')
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to save LED config')
    } finally {
      setIsLoading(null)
    }
  }

  const handleSaveMqttConfig = async () => {
    setIsLoading('mqtt')
    try {
      const response = await fetch('/api/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mqtt: {
            enabled: mqttConfig.enabled,
            broker: mqttConfig.broker,
            port: mqttConfig.port,
            username: mqttConfig.username,
            password: mqttConfig.password,
            device_name: mqttConfig.device_name,
            device_id: mqttConfig.device_id,
            client_id: mqttConfig.client_id,
            discovery_prefix: mqttConfig.discovery_prefix,
          },
        }),
      })
      if (response.ok) {
        toast.success('MQTT configuration saved. Restart required.')
      }
    } catch (error) {
      toast.error('Failed to save MQTT config')
    } finally {
      setIsLoading(null)
    }
  }

  return (
    <div className="flex flex-col w-full max-w-5xl mx-auto gap-6 py-6 px-4">
      {/* Page Header */}
      <div className="space-y-1">
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          Configure your sand table and application preferences
        </p>
      </div>

      <Separator />

      <Accordion
        type="multiple"
        value={openSections}
        onValueChange={handleAccordionChange}
        className="space-y-4"
      >
        {/* Device Connection */}
        <AccordionItem value="connection" id="section-connection" className="border rounded-lg px-4 overflow-visible">
          <AccordionTrigger className="hover:no-underline">
            <div className="flex items-center gap-3">
              <span className="material-icons-outlined text-muted-foreground">
                usb
              </span>
              <div className="text-left">
                <div className="font-semibold">Device Connection</div>
                <div className="text-sm text-muted-foreground font-normal">
                  Serial port configuration
                </div>
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent className="pt-4 pb-6 space-y-6">
            {/* Connection Status */}
            <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-lg ${isConnected ? 'bg-green-100 dark:bg-green-900' : 'bg-muted'}`}>
                  <span className={`material-icons ${isConnected ? 'text-green-600' : 'text-muted-foreground'}`}>
                    {isConnected ? 'usb' : 'usb_off'}
                  </span>
                </div>
                <div>
                  <p className="font-medium">Status</p>
                  <p className={`text-sm ${isConnected ? 'text-green-600' : 'text-destructive'}`}>
                    {connectionStatus}
                  </p>
                </div>
              </div>
              {isConnected && (
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={handleDisconnect}
                  disabled={isLoading === 'disconnect'}
                >
                  Disconnect
                </Button>
              )}
            </div>

            {/* Port Selection */}
            <div className="space-y-3">
              <Label>Available Serial Ports</Label>
              <div className="flex gap-3">
                <Select value={selectedPort} onValueChange={setSelectedPort}>
                  <SelectTrigger className="flex-1">
                    <SelectValue placeholder="Select a port..." />
                  </SelectTrigger>
                  <SelectContent>
                    {ports.length === 0 ? (
                      <div className="py-6 text-center text-sm text-muted-foreground">
                        No serial ports found
                      </div>
                    ) : (
                      ports.map((port) => (
                        <SelectItem key={port.port} value={port.port}>
                          {port.port} - {port.description}
                        </SelectItem>
                      ))
                    )}
                  </SelectContent>
                </Select>
                <Button
                  onClick={handleConnect}
                  disabled={isLoading === 'connect' || !selectedPort || isConnected}
                  className="gap-2"
                >
                  {isLoading === 'connect' ? (
                    <span className="material-icons-outlined animate-spin">sync</span>
                  ) : (
                    <span className="material-icons-outlined">cable</span>
                  )}
                  Connect
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Select a port and click 'Connect' to establish a connection.
              </p>
            </div>
          </AccordionContent>
        </AccordionItem>

        {/* Application Settings */}
        <AccordionItem value="application" id="section-application" className="border rounded-lg px-4 overflow-visible">
          <AccordionTrigger className="hover:no-underline">
            <div className="flex items-center gap-3">
              <span className="material-icons-outlined text-muted-foreground">
                tune
              </span>
              <div className="text-left">
                <div className="font-semibold">Application Settings</div>
                <div className="text-sm text-muted-foreground font-normal">
                  Customize app name and branding
                </div>
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent className="pt-4 pb-6 space-y-6">
            {/* Custom Logo */}
            <div className="space-y-3">
              <Label>Custom Logo</Label>
              <div className="flex items-center gap-4 p-4 bg-muted/50 rounded-lg">
                <div className="w-16 h-16 rounded-full overflow-hidden border bg-background flex items-center justify-center shrink-0">
                  {settings.custom_logo ? (
                    <img
                      src={`/static/custom/${settings.custom_logo}`}
                      alt="Custom Logo"
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <img
                      src="/static/android-chrome-192x192.png"
                      alt="Default Logo"
                      className="w-full h-full object-cover"
                    />
                  )}
                </div>
                <div className="flex-1">
                  <p className="font-medium">
                    {settings.custom_logo ? 'Custom logo active' : 'Using default logo'}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    PNG, JPG, GIF, WebP or SVG (max 5MB)
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-2"
                    disabled={isLoading === 'logo'}
                    onClick={() => document.getElementById('logo-upload')?.click()}
                  >
                    {isLoading === 'logo' ? (
                      <span className="material-icons-outlined animate-spin text-base">sync</span>
                    ) : (
                      <span className="material-icons-outlined text-base">upload</span>
                    )}
                    Upload
                  </Button>
                  {settings.custom_logo && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-2 text-destructive hover:text-destructive"
                      disabled={isLoading === 'logo'}
                      onClick={handleDeleteLogo}
                    >
                      <span className="material-icons-outlined text-base">delete</span>
                    </Button>
                  )}
                </div>
                <input
                  id="logo-upload"
                  type="file"
                  accept=".png,.jpg,.jpeg,.gif,.webp,.svg"
                  className="hidden"
                  onChange={handleLogoUpload}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                A favicon will be automatically generated from your logo.
              </p>
            </div>

            <Separator />

            {/* App Name */}
            <div className="space-y-3">
              <Label htmlFor="appName">Application Name</Label>
              <div className="flex gap-3">
                <div className="relative flex-1">
                  <Input
                    id="appName"
                    value={settings.app_name || ''}
                    onChange={(e) =>
                      setSettings({ ...settings, app_name: e.target.value })
                    }
                    placeholder="e.g., Dune Weaver"
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7 p-0"
                    onClick={() => setSettings({ ...settings, app_name: 'Dune Weaver' })}
                  >
                    <span className="material-icons text-base">restart_alt</span>
                  </Button>
                </div>
                <Button
                  onClick={handleSaveAppName}
                  disabled={isLoading === 'appName'}
                  className="gap-2"
                >
                  {isLoading === 'appName' ? (
                    <span className="material-icons-outlined animate-spin">sync</span>
                  ) : (
                    <span className="material-icons-outlined">save</span>
                  )}
                  Save
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                This name appears in the browser tab and header.
              </p>
            </div>
          </AccordionContent>
        </AccordionItem>

        {/* LED Controller Configuration */}
        <AccordionItem value="led" id="section-led" className="border rounded-lg px-4 overflow-visible">
          <AccordionTrigger className="hover:no-underline">
            <div className="flex items-center gap-3">
              <span className="material-icons-outlined text-muted-foreground">
                lightbulb
              </span>
              <div className="text-left">
                <div className="font-semibold">LED Controller</div>
                <div className="text-sm text-muted-foreground font-normal">
                  WLED or local GPIO LED control
                </div>
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent className="pt-4 pb-6 space-y-6">
            {/* LED Provider Selection */}
            <div className="space-y-3">
              <Label>LED Provider</Label>
              <RadioGroup
                value={ledConfig.provider}
                onValueChange={(value) =>
                  setLedConfig({ ...ledConfig, provider: value as LedConfig['provider'] })
                }
                className="flex gap-4"
              >
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="none" id="led-none" />
                  <Label htmlFor="led-none" className="font-normal">None</Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="wled" id="led-wled" />
                  <Label htmlFor="led-wled" className="font-normal">WLED</Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="dw_leds" id="led-dw" />
                  <Label htmlFor="led-dw" className="font-normal">DW LEDs (GPIO)</Label>
                </div>
              </RadioGroup>
            </div>

            {/* WLED Config */}
            {ledConfig.provider === 'wled' && (
              <div className="space-y-3 p-4 bg-muted/50 rounded-lg">
                <Label htmlFor="wledIp">WLED IP Address</Label>
                <Input
                  id="wledIp"
                  value={ledConfig.wled_ip || ''}
                  onChange={(e) =>
                    setLedConfig({ ...ledConfig, wled_ip: e.target.value })
                  }
                  placeholder="e.g., 192.168.1.100"
                />
                <p className="text-xs text-muted-foreground">
                  Enter the IP address of your WLED controller
                </p>
              </div>
            )}

            {/* DW LEDs Config */}
            {ledConfig.provider === 'dw_leds' && (
              <div className="space-y-4 p-4 bg-muted/50 rounded-lg">
                <Alert className="flex items-start">
                  <span className="material-icons-outlined text-base mr-2 shrink-0">info</span>
                  <AlertDescription>
                    Supports WS2812, WS2812B, SK6812 and other WS281x LED strips
                  </AlertDescription>
                </Alert>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="numLeds">Number of LEDs</Label>
                    <Input
                      id="numLeds"
                      type="number"
                      value={ledConfig.num_leds || 60}
                      onChange={(e) =>
                        setLedConfig({ ...ledConfig, num_leds: parseInt(e.target.value) })
                      }
                      min={1}
                      max={1000}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="gpioPin">GPIO Pin</Label>
                    <Select
                      value={String(ledConfig.gpio_pin || 18)}
                      onValueChange={(value) =>
                        setLedConfig({ ...ledConfig, gpio_pin: parseInt(value) })
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="12">GPIO 12 (PWM0)</SelectItem>
                        <SelectItem value="13">GPIO 13 (PWM1)</SelectItem>
                        <SelectItem value="18">GPIO 18 (PWM0)</SelectItem>
                        <SelectItem value="19">GPIO 19 (PWM1)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="pixelOrder">Pixel Color Order</Label>
                  <Select
                    value={ledConfig.pixel_order || 'GRB'}
                    onValueChange={(value) =>
                      setLedConfig({ ...ledConfig, pixel_order: value })
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="GRB">GRB - WS2812/WS2812B (most common)</SelectItem>
                      <SelectItem value="RGB">RGB - WS2815/WS2811</SelectItem>
                      <SelectItem value="GRBW">GRBW - SK6812 RGBW</SelectItem>
                      <SelectItem value="RGBW">RGBW - SK6812 variant</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            <Button
              onClick={handleSaveLedConfig}
              disabled={isLoading === 'led'}
              className="gap-2"
            >
              {isLoading === 'led' ? (
                <span className="material-icons-outlined animate-spin">sync</span>
              ) : (
                <span className="material-icons-outlined">save</span>
              )}
              Save LED Configuration
            </Button>
          </AccordionContent>
        </AccordionItem>

        {/* Home Assistant Integration */}
        <AccordionItem value="mqtt" id="section-mqtt" className="border rounded-lg px-4 overflow-visible">
          <AccordionTrigger className="hover:no-underline">
            <div className="flex items-center gap-3">
              <span className="material-icons-outlined text-muted-foreground">
                home
              </span>
              <div className="text-left">
                <div className="font-semibold">Home Assistant Integration</div>
                <div className="text-sm text-muted-foreground font-normal">
                  MQTT configuration for smart home control
                </div>
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent className="pt-4 pb-6 space-y-6">
            {/* Enable Toggle */}
            <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
              <div>
                <p className="font-medium">Enable MQTT</p>
                <p className="text-sm text-muted-foreground">
                  Connect to Home Assistant via MQTT
                </p>
              </div>
              <Switch
                checked={mqttConfig.enabled}
                onCheckedChange={(checked) =>
                  setMqttConfig({ ...mqttConfig, enabled: checked })
                }
              />
            </div>

            {mqttConfig.enabled && (
              <div className="space-y-4">
                {/* Broker Settings */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="mqttBroker">
                      Broker Address <span className="text-destructive">*</span>
                    </Label>
                    <Input
                      id="mqttBroker"
                      value={mqttConfig.broker || ''}
                      onChange={(e) =>
                        setMqttConfig({ ...mqttConfig, broker: e.target.value })
                      }
                      placeholder="e.g., 192.168.1.100"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="mqttPort">Port</Label>
                    <Input
                      id="mqttPort"
                      type="number"
                      value={mqttConfig.port || 1883}
                      onChange={(e) =>
                        setMqttConfig({ ...mqttConfig, port: parseInt(e.target.value) })
                      }
                      placeholder="1883"
                    />
                  </div>
                </div>

                {/* Authentication */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="mqttUser">Username</Label>
                    <Input
                      id="mqttUser"
                      value={mqttConfig.username || ''}
                      onChange={(e) =>
                        setMqttConfig({ ...mqttConfig, username: e.target.value })
                      }
                      placeholder="Optional"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="mqttPass">Password</Label>
                    <Input
                      id="mqttPass"
                      type="password"
                      value={mqttConfig.password || ''}
                      onChange={(e) =>
                        setMqttConfig({ ...mqttConfig, password: e.target.value })
                      }
                      placeholder="Optional"
                    />
                  </div>
                </div>

                <Separator />

                {/* Device Settings */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="mqttDeviceName">Device Name</Label>
                    <Input
                      id="mqttDeviceName"
                      value={mqttConfig.device_name || 'Dune Weaver'}
                      onChange={(e) =>
                        setMqttConfig({ ...mqttConfig, device_name: e.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="mqttDeviceId">Device ID</Label>
                    <Input
                      id="mqttDeviceId"
                      value={mqttConfig.device_id || 'dune_weaver'}
                      onChange={(e) =>
                        setMqttConfig({ ...mqttConfig, device_id: e.target.value })
                      }
                    />
                  </div>
                </div>

                <Alert className="flex items-start">
                  <span className="material-icons-outlined text-base mr-2 shrink-0">info</span>
                  <AlertDescription>
                    MQTT configuration changes require a restart to take effect.
                  </AlertDescription>
                </Alert>
              </div>
            )}

            <Button
              onClick={handleSaveMqttConfig}
              disabled={isLoading === 'mqtt'}
              className="gap-2"
            >
              {isLoading === 'mqtt' ? (
                <span className="material-icons-outlined animate-spin">sync</span>
              ) : (
                <span className="material-icons-outlined">save</span>
              )}
              Save MQTT Configuration
            </Button>
          </AccordionContent>
        </AccordionItem>

        {/* Auto-play on Boot */}
        <AccordionItem value="autoplay" id="section-autoplay" className="border rounded-lg px-4 overflow-visible">
          <AccordionTrigger className="hover:no-underline">
            <div className="flex items-center gap-3">
              <span className="material-icons-outlined text-muted-foreground">
                play_circle
              </span>
              <div className="text-left">
                <div className="font-semibold">Auto-play on Boot</div>
                <div className="text-sm text-muted-foreground font-normal">
                  Start a playlist automatically on startup
                </div>
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent className="pt-4 pb-6 space-y-6">
            <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
              <div>
                <p className="font-medium">Enable Auto-play</p>
                <p className="text-sm text-muted-foreground">
                  Automatically start playing when the system boots
                </p>
              </div>
              <Switch
                checked={autoPlayEnabled}
                onCheckedChange={setAutoPlayEnabled}
              />
            </div>

            {autoPlayEnabled && (
              <div className="space-y-4 p-4 bg-muted/50 rounded-lg">
                <div className="space-y-2">
                  <Label>Startup Playlist</Label>
                  <Select>
                    <SelectTrigger>
                      <SelectValue placeholder="Select a playlist..." />
                    </SelectTrigger>
                    <SelectContent>
                      {playlists.map((playlist) => (
                        <SelectItem key={playlist} value={playlist}>
                          {playlist}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Run Mode</Label>
                    <Select defaultValue="loop">
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="single">Single (play once)</SelectItem>
                        <SelectItem value="loop">Loop (repeat forever)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Pause Between Patterns (s)</Label>
                    <Input type="number" defaultValue="5" min="0" step="0.5" />
                  </div>
                </div>
              </div>
            )}
          </AccordionContent>
        </AccordionItem>

        {/* Still Sands */}
        <AccordionItem value="stillsands" id="section-stillsands" className="border rounded-lg px-4 overflow-visible">
          <AccordionTrigger className="hover:no-underline">
            <div className="flex items-center gap-3">
              <span className="material-icons-outlined text-muted-foreground">
                bedtime
              </span>
              <div className="text-left">
                <div className="font-semibold">Still Sands</div>
                <div className="text-sm text-muted-foreground font-normal">
                  Schedule quiet periods for your table
                </div>
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent className="pt-4 pb-6 space-y-6">
            <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
              <div>
                <p className="font-medium">Enable Still Sands</p>
                <p className="text-sm text-muted-foreground">
                  Pause the table during specified time periods
                </p>
              </div>
              <Switch
                checked={stillSandsEnabled}
                onCheckedChange={setStillSandsEnabled}
              />
            </div>

            {stillSandsEnabled && (
              <Alert className="flex items-start">
                <span className="material-icons-outlined text-base mr-2 shrink-0">schedule</span>
                <AlertDescription>
                  Configure time periods when the sand table should rest.
                  Patterns will resume automatically when still periods end.
                </AlertDescription>
              </Alert>
            )}
          </AccordionContent>
        </AccordionItem>

        {/* Software Version */}
        <AccordionItem value="version" id="section-version" className="border rounded-lg px-4 overflow-visible">
          <AccordionTrigger className="hover:no-underline">
            <div className="flex items-center gap-3">
              <span className="material-icons-outlined text-muted-foreground">
                info
              </span>
              <div className="text-left">
                <div className="font-semibold">Software Version</div>
                <div className="text-sm text-muted-foreground font-normal">
                  Updates and system information
                </div>
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent className="pt-4 pb-6 space-y-4">
            <div className="flex items-center gap-4 p-4 bg-muted/50 rounded-lg">
              <div className="p-2 bg-muted rounded-lg">
                <span className="material-icons text-muted-foreground">terminal</span>
              </div>
              <div className="flex-1">
                <p className="font-medium">Current Version</p>
                <p className="text-sm text-muted-foreground">v1.0.0</p>
              </div>
            </div>

            <div className="flex items-center gap-4 p-4 bg-muted/50 rounded-lg">
              <div className="p-2 bg-muted rounded-lg">
                <span className="material-icons text-muted-foreground">system_update</span>
              </div>
              <div className="flex-1">
                <p className="font-medium">Latest Version</p>
                <p className="text-sm text-muted-foreground">Checking...</p>
              </div>
              <Button variant="secondary" size="sm" disabled>
                <span className="material-icons-outlined text-base mr-1">download</span>
                Update
              </Button>
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  )
}
