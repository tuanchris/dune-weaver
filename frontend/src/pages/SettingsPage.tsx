import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { apiClient } from '@/lib/apiClient'
import { useOnBackendConnected } from '@/hooks/useBackendConnection'
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
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { SearchableSelect } from '@/components/ui/searchable-select'

// Types

interface Settings {
  app_name?: string
  custom_logo?: string
  preferred_port?: string
  // Machine settings
  table_type_override?: string
  detected_table_type?: string
  effective_table_type?: string
  gear_ratio?: number
  x_steps_per_mm?: number
  y_steps_per_mm?: number
  available_table_types?: { value: string; label: string }[]
  // Homing settings
  homing_mode?: number
  angular_offset?: number
  auto_home_enabled?: boolean
  auto_home_after_patterns?: number
  // Pattern clearing settings
  clear_pattern_speed?: number
  custom_clear_from_in?: string
  custom_clear_from_out?: string
}

interface TimeSlot {
  start_time: string
  end_time: string
  days: 'daily' | 'weekdays' | 'weekends' | 'custom'
  custom_days?: string[]
}

interface StillSandsSettings {
  enabled: boolean
  finish_pattern: boolean
  control_wled: boolean
  timezone: string
  time_slots: TimeSlot[]
}

interface AutoPlaySettings {
  enabled: boolean
  playlist: string
  run_mode: 'single' | 'loop'
  pause_time: number
  clear_pattern: string
  shuffle: boolean
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
  const [ports, setPorts] = useState<string[]>([])
  const [selectedPort, setSelectedPort] = useState('')
  const [isConnected, setIsConnected] = useState(false)
  const [connectionStatus, setConnectionStatus] = useState('Disconnected')

  // Settings state
  const [settings, setSettings] = useState<Settings>({})
  const [ledConfig, setLedConfig] = useState<LedConfig>({ provider: 'none', gpio_pin: 18 })
  const [numLedsInput, setNumLedsInput] = useState('60')
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
  const [autoPlaySettings, setAutoPlaySettings] = useState<AutoPlaySettings>({
    enabled: false,
    playlist: '',
    run_mode: 'loop',
    pause_time: 5,
    clear_pattern: 'adaptive',
    shuffle: false,
  })
  const [autoPlayPauseUnit, setAutoPlayPauseUnit] = useState<'sec' | 'min' | 'hr'>('min')
  const [autoPlayPauseValue, setAutoPlayPauseValue] = useState(5)
  const [autoPlayPauseInput, setAutoPlayPauseInput] = useState('5')
  const [playlists, setPlaylists] = useState<string[]>([])

  // Convert pause time from seconds to value + unit for display
  const secondsToDisplayPause = (seconds: number): { value: number; unit: 'sec' | 'min' | 'hr' } => {
    if (seconds >= 3600 && seconds % 3600 === 0) {
      return { value: seconds / 3600, unit: 'hr' }
    } else if (seconds >= 60 && seconds % 60 === 0) {
      return { value: seconds / 60, unit: 'min' }
    }
    return { value: seconds, unit: 'sec' }
  }

  // Convert display value + unit to seconds
  const displayPauseToSeconds = (value: number, unit: 'sec' | 'min' | 'hr'): number => {
    switch (unit) {
      case 'hr': return value * 3600
      case 'min': return value * 60
      default: return value
    }
  }

  // Still Sands state
  const [stillSandsSettings, setStillSandsSettings] = useState<StillSandsSettings>({
    enabled: false,
    finish_pattern: false,
    control_wled: false,
    timezone: '',
    time_slots: [],
  })

  // Pattern search state for clearing patterns
  const [patternFiles, setPatternFiles] = useState<string[]>([])

  // Version state
  const [versionInfo, setVersionInfo] = useState<{
    current: string
    latest: string
    update_available: boolean
  } | null>(null)

  // Helper to scroll to element with header offset
  const scrollToSection = (sectionId: string) => {
    const element = document.getElementById(`section-${sectionId}`)
    if (element) {
      const headerHeight = 80 // Header height + some padding
      const elementTop = element.getBoundingClientRect().top + window.scrollY
      window.scrollTo({ top: elementTop - headerHeight, behavior: 'smooth' })
    }
  }

  // Scroll to section and clear URL param after navigation
  useEffect(() => {
    if (sectionParam) {
      // Scroll to the section after a short delay to allow render
      setTimeout(() => {
        scrollToSection(sectionParam)
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
        // Also load settings for preferred port
        if (!loadedSections.has('_settings')) {
          setLoadedSections((prev) => new Set(prev).add('_settings'))
          await fetchSettings()
        }
        break
      case 'application':
      case 'mqtt':
      case 'autoplay':
      case 'stillsands':
      case 'machine':
      case 'homing':
      case 'clearing':
        // These all share settings data
        if (!loadedSections.has('_settings')) {
          setLoadedSections((prev) => new Set(prev).add('_settings'))
          await fetchSettings()
        }
        if ((section === 'autoplay' || section === 'clearing') && !loadedSections.has('_playlists')) {
          setLoadedSections((prev) => new Set(prev).add('_playlists'))
          await fetchPlaylists()
        }
        if (section === 'clearing' && !loadedSections.has('_patterns')) {
          setLoadedSections((prev) => new Set(prev).add('_patterns'))
          await fetchPatternFiles()
        }
        break
      case 'led':
        await fetchLedConfig()
        break
      case 'version':
        await fetchVersionInfo()
        break
    }
  }

  const fetchPatternFiles = async () => {
    try {
      const data = await apiClient.get<string[]>('/list_theta_rho_files')
      // Response is a flat array of file paths
      setPatternFiles(Array.isArray(data) ? data : [])
    } catch (error) {
      console.error('Error fetching pattern files:', error)
    }
  }

  const fetchVersionInfo = async () => {
    try {
      const data = await apiClient.get<{ current: string; latest: string; update_available: boolean }>('/api/version')
      setVersionInfo(data)
    } catch (error) {
      console.error('Failed to fetch version info:', error)
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
        scrollToSection(newlyOpened)
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
      // Fetch available ports first
      const portsData = await apiClient.get<string[]>('/list_serial_ports')
      const availablePorts = portsData || []
      setPorts(availablePorts)

      // Fetch connection status
      const statusData = await apiClient.get<{ connected: boolean; port?: string }>('/serial_status')
      setIsConnected(statusData.connected || false)
      setConnectionStatus(statusData.connected ? 'Connected' : 'Disconnected')

      // Only set selectedPort if it exists in the available ports list
      // This prevents race conditions where stale port data from a different
      // backend (e.g., Mac port on a Pi) could be set
      if (statusData.port && availablePorts.includes(statusData.port)) {
        setSelectedPort(statusData.port)
      } else if (statusData.port && !availablePorts.includes(statusData.port)) {
        // Port from status doesn't exist on this machine - likely stale data
        console.warn(`Port ${statusData.port} from status not in available ports, ignoring`)
        setSelectedPort('')
      }
    } catch (error) {
      console.error('Error fetching ports:', error)
    }
  }

  // Always fetch ports on mount since connection is the default section
  useEffect(() => {
    fetchPorts()
  }, [])

  // Refetch when backend reconnects
  useOnBackendConnected(() => {
    fetchPorts()
  })

  const fetchSettings = async () => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const data = await apiClient.get<Record<string, any>>('/api/settings')
      // Map the nested API response to our flat Settings interface
      setSettings({
        app_name: data.app?.name,
        custom_logo: data.app?.custom_logo,
        preferred_port: data.connection?.preferred_port,
        // Machine settings
        table_type_override: data.machine?.table_type_override,
        detected_table_type: data.machine?.detected_table_type,
        effective_table_type: data.machine?.effective_table_type,
        gear_ratio: data.machine?.gear_ratio,
        x_steps_per_mm: data.machine?.x_steps_per_mm,
        y_steps_per_mm: data.machine?.y_steps_per_mm,
        available_table_types: data.machine?.available_table_types,
        // Homing settings
        homing_mode: data.homing?.mode,
        angular_offset: data.homing?.angular_offset_degrees,
        auto_home_enabled: data.homing?.auto_home_enabled,
        auto_home_after_patterns: data.homing?.auto_home_after_patterns,
        // Pattern clearing settings
        clear_pattern_speed: data.patterns?.clear_pattern_speed,
        custom_clear_from_in: data.patterns?.custom_clear_from_in,
        custom_clear_from_out: data.patterns?.custom_clear_from_out,
      })
      // Set auto-play settings
      if (data.auto_play) {
        const pauseSeconds = data.auto_play.pause_time ?? 300 // Default 5 minutes
        const { value, unit } = secondsToDisplayPause(pauseSeconds)
        setAutoPlayPauseValue(value)
        setAutoPlayPauseInput(String(value))
        setAutoPlayPauseUnit(unit)
        setAutoPlaySettings({
          enabled: data.auto_play.enabled || false,
          playlist: data.auto_play.playlist || '',
          run_mode: data.auto_play.run_mode || 'loop',
          pause_time: pauseSeconds,
          clear_pattern: data.auto_play.clear_pattern || 'adaptive',
          shuffle: data.auto_play.shuffle || false,
        })
      }
      // Set still sands settings
      if (data.scheduled_pause) {
        setStillSandsSettings({
          enabled: data.scheduled_pause.enabled || false,
          finish_pattern: data.scheduled_pause.finish_pattern || false,
          control_wled: data.scheduled_pause.control_wled || false,
          timezone: data.scheduled_pause.timezone || '',
          time_slots: data.scheduled_pause.time_slots || [],
        })
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
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const data = await apiClient.get<Record<string, any>>('/get_led_config')
      setLedConfig({
        provider: data.provider || 'none',
        wled_ip: data.wled_ip,
        num_leds: data.dw_led_num_leds,
        gpio_pin: data.dw_led_gpio_pin,
        pixel_order: data.dw_led_pixel_order,
      })
      setNumLedsInput(String(data.dw_led_num_leds || 60))
    } catch (error) {
      console.error('Error fetching LED config:', error)
    }
  }

  const fetchPlaylists = async () => {
    try {
      const data = await apiClient.get('/list_all_playlists')
      // Backend returns array directly, not { playlists: [...] }
      setPlaylists(Array.isArray(data) ? data : [])
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
      const data = await apiClient.post<{ success?: boolean; message?: string }>('/connect', { port: selectedPort })
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
      const data = await apiClient.post<{ success?: boolean }>('/disconnect')
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

  const handleSavePreferredPort = async () => {
    setIsLoading('preferredPort')
    try {
      // Send the actual value: __auto__, __none__, or specific port
      const portValue = settings.preferred_port || '__auto__'
      await apiClient.patch('/api/settings', {
        connection: { preferred_port: portValue },
      })
      if (!settings.preferred_port || settings.preferred_port === '__auto__') {
        toast.success('Auto-connect: Auto (first available port)')
      } else if (settings.preferred_port === '__none__') {
        toast.success('Auto-connect: Disabled')
      } else {
        toast.success(`Auto-connect: ${settings.preferred_port}`)
      }
    } catch (error) {
      toast.error('Failed to save auto-connect setting')
    } finally {
      setIsLoading(null)
    }
  }

  const handleSaveAppName = async () => {
    setIsLoading('appName')
    try {
      await apiClient.patch('/api/settings', { app: { name: settings.app_name } })
      toast.success('App name saved. Refresh to see changes.')
    } catch (error) {
      toast.error('Failed to save app name')
    } finally {
      setIsLoading(null)
    }
  }

  // Update favicon links in the document head and notify Layout to refresh
  const updateBranding = (customLogo: string | null) => {
    const timestamp = Date.now() // Cache buster

    // Update favicon links (use apiClient.getAssetUrl for multi-table support)
    const faviconIco = document.getElementById('favicon-ico') as HTMLLinkElement
    const appleTouchIcon = document.getElementById('apple-touch-icon') as HTMLLinkElement

    if (customLogo) {
      if (faviconIco) faviconIco.href = apiClient.getAssetUrl(`/static/custom/favicon.ico?v=${timestamp}`)
      if (appleTouchIcon) appleTouchIcon.href = apiClient.getAssetUrl(`/static/custom/${customLogo}?v=${timestamp}`)
    } else {
      if (faviconIco) faviconIco.href = apiClient.getAssetUrl(`/static/favicon.ico?v=${timestamp}`)
      if (appleTouchIcon) appleTouchIcon.href = apiClient.getAssetUrl(`/static/apple-touch-icon.png?v=${timestamp}`)
    }

    // Dispatch event for Layout to update header logo
    window.dispatchEvent(new CustomEvent('branding-updated'))
  }

  const handleLogoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    setIsLoading('logo')
    try {
      const data = await apiClient.uploadFile('/api/upload-logo', file, 'file') as { filename: string }
      setSettings({ ...settings, custom_logo: data.filename })
      updateBranding(data.filename)
      toast.success('Logo uploaded!')
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
      await apiClient.delete('/api/custom-logo')
      setSettings({ ...settings, custom_logo: undefined })
      updateBranding(null)
      toast.success('Logo removed!')
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
      await apiClient.post('/set_led_config', {
        provider: ledConfig.provider,
        ip_address: ledConfig.wled_ip,
        num_leds: ledConfig.num_leds,
        gpio_pin: ledConfig.gpio_pin,
        pixel_order: ledConfig.pixel_order,
      })
      toast.success('LED configuration saved')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to save LED config')
    } finally {
      setIsLoading(null)
    }
  }

  const handleSaveMqttConfig = async () => {
    setIsLoading('mqtt')
    try {
      await apiClient.patch('/api/settings', {
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
      })
      toast.success('MQTT configuration saved. Restart required.')
    } catch (error) {
      toast.error('Failed to save MQTT config')
    } finally {
      setIsLoading(null)
    }
  }

  const handleTestMqttConnection = async () => {
    if (!mqttConfig.broker) {
      toast.error('Please enter a broker address')
      return
    }
    setIsLoading('mqttTest')
    try {
      const data = await apiClient.post<{ success?: boolean; error?: string }>('/api/mqtt-test', {
        broker: mqttConfig.broker,
        port: mqttConfig.port || 1883,
        username: mqttConfig.username || '',
        password: mqttConfig.password || '',
      })
      if (data.success) {
        toast.success('MQTT connection successful!')
      } else {
        toast.error(data.error || 'Connection failed')
      }
    } catch (error) {
      toast.error('Failed to test MQTT connection')
    } finally {
      setIsLoading(null)
    }
  }

  const handleSaveMachineSettings = async () => {
    setIsLoading('machine')
    try {
      await apiClient.patch('/api/settings', {
        machine: {
          table_type_override: settings.table_type_override || '',
        },
      })
      toast.success('Machine settings saved')
    } catch (error) {
      toast.error('Failed to save machine settings')
    } finally {
      setIsLoading(null)
    }
  }

  const handleSaveHomingConfig = async () => {
    setIsLoading('homing')
    try {
      await apiClient.patch('/api/settings', {
        homing: {
          mode: settings.homing_mode,
          angular_offset_degrees: settings.angular_offset,
          auto_home_enabled: settings.auto_home_enabled,
          auto_home_after_patterns: settings.auto_home_after_patterns,
        },
      })
      toast.success('Homing configuration saved')
    } catch (error) {
      toast.error('Failed to save homing configuration')
    } finally {
      setIsLoading(null)
    }
  }

  const handleSaveClearingSettings = async () => {
    setIsLoading('clearing')
    try {
      await apiClient.patch('/api/settings', {
        patterns: {
          // Send 0 to indicate "reset to default" - backend interprets 0 or negative as None
          clear_pattern_speed: settings.clear_pattern_speed ?? 0,
          custom_clear_from_in: settings.custom_clear_from_in || null,
          custom_clear_from_out: settings.custom_clear_from_out || null,
        },
      })
      toast.success('Clearing settings saved')
    } catch (error) {
      toast.error('Failed to save clearing settings')
    } finally {
      setIsLoading(null)
    }
  }

  const handleSaveAutoPlaySettings = async () => {
    setIsLoading('autoplay')
    try {
      // Convert pause value + unit to seconds
      const pauseTimeSeconds = displayPauseToSeconds(autoPlayPauseValue, autoPlayPauseUnit)
      await apiClient.patch('/api/settings', {
        auto_play: {
          ...autoPlaySettings,
          pause_time: pauseTimeSeconds,
        },
      })
      toast.success('Auto-play settings saved')
    } catch (error) {
      toast.error('Failed to save auto-play settings')
    } finally {
      setIsLoading(null)
    }
  }

  const handleSaveStillSandsSettings = async () => {
    setIsLoading('stillsands')
    try {
      await apiClient.patch('/api/settings', {
        scheduled_pause: stillSandsSettings,
      })
      toast.success('Still Sands settings saved')
    } catch (error) {
      toast.error('Failed to save Still Sands settings')
    } finally {
      setIsLoading(null)
    }
  }

  const addTimeSlot = () => {
    setStillSandsSettings({
      ...stillSandsSettings,
      time_slots: [
        ...stillSandsSettings.time_slots,
        { start_time: '22:00', end_time: '06:00', days: 'daily' },
      ],
    })
  }

  const removeTimeSlot = (index: number) => {
    setStillSandsSettings({
      ...stillSandsSettings,
      time_slots: stillSandsSettings.time_slots.filter((_, i) => i !== index),
    })
  }

  const updateTimeSlot = (index: number, updates: Partial<TimeSlot>) => {
    const newSlots = [...stillSandsSettings.time_slots]
    newSlots[index] = { ...newSlots[index], ...updates }
    setStillSandsSettings({ ...stillSandsSettings, time_slots: newSlots })
  }

  return (
    <div className="flex flex-col w-full max-w-5xl mx-auto gap-6 py-3 sm:py-6 px-0 sm:px-4">
      {/* Page Header */}
      <div className="space-y-0.5 sm:space-y-1 pl-1">
        <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
        <p className="text-xs text-muted-foreground">
          Configure your sand table
        </p>
      </div>

      <Separator />

      <Accordion
        type="multiple"
        value={openSections}
        onValueChange={handleAccordionChange}
        className="space-y-3"
      >
        {/* Device Connection */}
        <AccordionItem value="connection" id="section-connection" className="border rounded-lg px-4 overflow-visible bg-card">
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
            <div className="flex items-center justify-between p-4 rounded-lg border">
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 flex items-center justify-center rounded-lg ${isConnected ? 'bg-green-100 dark:bg-green-900' : 'bg-muted'}`}>
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
                        <SelectItem key={port} value={port}>
                          {port}
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

            <Separator />

            {/* Preferred Port for Auto-Connect */}
            <div className="space-y-3">
              <Label>Auto-Connect</Label>
              <div className="flex gap-3">
                <Select
                  value={settings.preferred_port || '__auto__'}
                  onValueChange={(value) =>
                    setSettings({ ...settings, preferred_port: value === '__auto__' ? undefined : value })
                  }
                >
                  <SelectTrigger className="flex-1">
                    <SelectValue placeholder="Select auto-connect option..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__auto__">Auto (pick first available)</SelectItem>
                    <SelectItem value="__none__">Disabled (no auto-connect)</SelectItem>
                    {ports.length > 0 && (
                      <>
                        <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground">Available Ports</div>
                        {ports.map((port) => (
                          <SelectItem key={port} value={port}>
                            {port}
                          </SelectItem>
                        ))}
                      </>
                    )}
                  </SelectContent>
                </Select>
                <Button
                  onClick={handleSavePreferredPort}
                  disabled={isLoading === 'preferredPort'}
                  className="gap-2"
                >
                  {isLoading === 'preferredPort' ? (
                    <span className="material-icons-outlined animate-spin">sync</span>
                  ) : (
                    <span className="material-icons-outlined">save</span>
                  )}
                  Save
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Choose how the system connects on startup: Auto picks the first available port, Disabled requires manual connection, or select a specific port.
              </p>
            </div>
          </AccordionContent>
        </AccordionItem>

        {/* Machine Settings */}
        <AccordionItem value="machine" id="section-machine" className="border rounded-lg px-4 overflow-visible bg-card">
          <AccordionTrigger className="hover:no-underline">
            <div className="flex items-center gap-3">
              <span className="material-icons-outlined text-muted-foreground">
                precision_manufacturing
              </span>
              <div className="text-left">
                <div className="font-semibold">Machine Settings</div>
                <div className="text-sm text-muted-foreground font-normal">
                  Table type and hardware configuration
                </div>
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent className="pt-4 pb-6 space-y-6">
            {/* Hardware Parameters */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-3 rounded-lg bg-muted/50">
                <p className="text-xs text-muted-foreground">Detected Type</p>
                <p className="font-medium text-sm">{settings.detected_table_type || 'Unknown'}</p>
              </div>
              <div className="p-3 rounded-lg bg-muted/50">
                <p className="text-xs text-muted-foreground">Gear Ratio</p>
                <p className="font-medium text-sm">{settings.gear_ratio ?? '—'}</p>
              </div>
              <div className="p-3 rounded-lg bg-muted/50">
                <p className="text-xs text-muted-foreground">X Steps/mm</p>
                <p className="font-medium text-sm">{settings.x_steps_per_mm ?? '—'}</p>
              </div>
              <div className="p-3 rounded-lg bg-muted/50">
                <p className="text-xs text-muted-foreground">Y Steps/mm</p>
                <p className="font-medium text-sm">{settings.y_steps_per_mm ?? '—'}</p>
              </div>
            </div>

            {/* Table Type Override */}
            <div className="space-y-3">
              <Label>Table Type Override</Label>
              <div className="flex gap-3">
                <Select
                  value={settings.table_type_override || 'auto'}
                  onValueChange={(value) =>
                    setSettings({ ...settings, table_type_override: value === 'auto' ? undefined : value })
                  }
                >
                  <SelectTrigger className="flex-1">
                    <SelectValue placeholder="Auto-detect (use detected type)" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">Auto-detect (use detected type)</SelectItem>
                    {settings.available_table_types?.map((type) => (
                      <SelectItem key={type.value} value={type.value}>
                        {type.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  onClick={handleSaveMachineSettings}
                  disabled={isLoading === 'machine'}
                  className="gap-2"
                >
                  {isLoading === 'machine' ? (
                    <span className="material-icons-outlined animate-spin">sync</span>
                  ) : (
                    <span className="material-icons-outlined">save</span>
                  )}
                  Save
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Override the automatically detected table type. This affects gear ratio calculations and homing behavior.
              </p>
            </div>

            <Alert className="flex items-start">
              <span className="material-icons-outlined text-base mr-2 shrink-0">info</span>
              <AlertDescription>
                Table type is normally detected automatically from GRBL settings. Use override if auto-detection is incorrect for your hardware.
              </AlertDescription>
            </Alert>

          </AccordionContent>
        </AccordionItem>

        {/* Homing Configuration */}
        <AccordionItem value="homing" id="section-homing" className="border rounded-lg px-4 overflow-visible bg-card">
          <AccordionTrigger className="hover:no-underline">
            <div className="flex items-center gap-3">
              <span className="material-icons-outlined text-muted-foreground">
                home
              </span>
              <div className="text-left">
                <div className="font-semibold">Homing Configuration</div>
                <div className="text-sm text-muted-foreground font-normal">
                  Homing mode and auto-home settings
                </div>
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent className="pt-4 pb-6 space-y-6">
            {/* Homing Mode Selection */}
            <div className="space-y-3">
              <Label>Homing Mode</Label>
              <RadioGroup
                value={String(settings.homing_mode || 0)}
                onValueChange={(value) =>
                  setSettings({ ...settings, homing_mode: parseInt(value) })
                }
                className="space-y-3"
              >
                <div className="flex items-start gap-3 p-3 border rounded-lg cursor-pointer hover:bg-muted/50">
                  <RadioGroupItem value="0" id="homing-crash" className="mt-0.5" />
                  <div className="flex-1">
                    <Label htmlFor="homing-crash" className="font-medium cursor-pointer">
                      Crash Homing
                    </Label>
                    <p className="text-xs text-muted-foreground mt-1">
                      Y axis moves until physical stop, then theta and rho set to 0
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-3 p-3 border rounded-lg cursor-pointer hover:bg-muted/50">
                  <RadioGroupItem value="1" id="homing-sensor" className="mt-0.5" />
                  <div className="flex-1">
                    <Label htmlFor="homing-sensor" className="font-medium cursor-pointer">
                      Sensor Homing
                    </Label>
                    <p className="text-xs text-muted-foreground mt-1">
                      Homes both X and Y axes using sensors
                    </p>
                  </div>
                </div>
              </RadioGroup>
            </div>

            {/* Sensor Offset (only visible for sensor mode) */}
            {settings.homing_mode === 1 && (
              <div className="space-y-3">
                <Label htmlFor="angular-offset">Sensor Offset (degrees)</Label>
                <Input
                  id="angular-offset"
                  type="number"
                  min="0"
                  max="360"
                  step="0.1"
                  value={settings.angular_offset ?? ''}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      angular_offset: e.target.value === '' ? undefined : parseFloat(e.target.value),
                    })
                  }
                  placeholder="0.0"
                />
                <p className="text-xs text-muted-foreground">
                  Set the angle (in degrees) where your radial arm should be offset. Choose a value so the radial arm points East.
                </p>
              </div>
            )}

            {/* Auto-Home During Playlists */}
            <div className="p-4 rounded-lg border space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium flex items-center gap-2">
                    <span className="material-icons-outlined text-base">autorenew</span>
                    Auto-Home During Playlists
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Perform homing after a set number of patterns to maintain accuracy
                  </p>
                </div>
                <Switch
                  checked={settings.auto_home_enabled || false}
                  onCheckedChange={(checked) =>
                    setSettings({ ...settings, auto_home_enabled: checked })
                  }
                />
              </div>

              {settings.auto_home_enabled && (
                <div className="space-y-3">
                  <Label htmlFor="auto-home-patterns">Home after every X patterns</Label>
                  <Input
                    id="auto-home-patterns"
                    type="number"
                    min="1"
                    max="100"
                    value={settings.auto_home_after_patterns || 5}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        auto_home_after_patterns: parseInt(e.target.value) || 5,
                      })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Homing occurs after each main pattern completes (clear patterns don't count).
                  </p>
                </div>
              )}
            </div>

            <Button
              onClick={handleSaveHomingConfig}
              disabled={isLoading === 'homing'}
              className="gap-2"
            >
              {isLoading === 'homing' ? (
                <span className="material-icons-outlined animate-spin">sync</span>
              ) : (
                <span className="material-icons-outlined">save</span>
              )}
              Save Homing Configuration
            </Button>
          </AccordionContent>
        </AccordionItem>

        {/* Application Settings */}
        <AccordionItem value="application" id="section-application" className="border rounded-lg px-4 overflow-visible bg-card">
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
              <div className="flex flex-col sm:flex-row sm:items-center gap-4 p-4 rounded-lg border">
                <div className="flex items-center gap-4">
                  <div className="w-16 h-16 rounded-full overflow-hidden border bg-background flex items-center justify-center shrink-0">
                    {settings.custom_logo ? (
                      <img
                        src={apiClient.getAssetUrl(`/static/custom/${settings.custom_logo}`)}
                        alt="Custom Logo"
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <img
                        src={apiClient.getAssetUrl('/static/android-chrome-192x192.png')}
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
                </div>
                <div className="flex gap-2 sm:ml-auto">
                  <Button
                    variant="secondary"
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
                      variant="secondary"
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

        {/* Pattern Clearing */}
        <AccordionItem value="clearing" id="section-clearing" className="border rounded-lg px-4 overflow-visible bg-card">
          <AccordionTrigger className="hover:no-underline">
            <div className="flex items-center gap-3">
              <span className="material-icons-outlined text-muted-foreground">
                cleaning_services
              </span>
              <div className="text-left">
                <div className="font-semibold">Pattern Clearing</div>
                <div className="text-sm text-muted-foreground font-normal">
                  Customize clearing speed and patterns
                </div>
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent className="pt-4 pb-6 space-y-6">
            <p className="text-sm text-muted-foreground">
              Customize the clearing behavior used when transitioning between patterns.
            </p>

            {/* Clearing Speed */}
            <div className="p-4 rounded-lg border space-y-3">
              <h4 className="font-medium">Clearing Speed</h4>
              <p className="text-sm text-muted-foreground">
                Set a custom speed for clearing patterns. Leave empty to use the default pattern speed.
              </p>
              <div className="space-y-3">
                <Label htmlFor="clear-speed">Speed (steps per minute)</Label>
                <Input
                  id="clear-speed"
                  type="number"
                  min="50"
                  max="2000"
                  step="50"
                  value={settings.clear_pattern_speed || ''}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      clear_pattern_speed: e.target.value ? parseInt(e.target.value) : undefined,
                    })
                  }
                  placeholder="Default (use pattern speed)"
                />
              </div>
            </div>

            {/* Custom Clear Patterns */}
            <div className="p-4 rounded-lg border space-y-3">
              <h4 className="font-medium">Custom Clear Patterns</h4>
              <p className="text-sm text-muted-foreground">
                Choose specific patterns to use when clearing. Leave empty for default behavior.
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-3">
                  <Label htmlFor="clear-from-in">Clear From Center Pattern</Label>
                  <SearchableSelect
                    value={settings.custom_clear_from_in || '__default__'}
                    onValueChange={(value) =>
                      setSettings({ ...settings, custom_clear_from_in: value === '__default__' ? undefined : value })
                    }
                    options={[
                      { value: '__default__', label: 'Default (built-in)' },
                      ...patternFiles.map((file) => ({ value: file, label: file })),
                    ]}
                    placeholder="Default (built-in)"
                    searchPlaceholder="Search patterns..."
                    emptyMessage="No patterns found"
                  />
                  <p className="text-xs text-muted-foreground">
                    Pattern used when clearing from center outward.
                  </p>
                </div>

                <div className="space-y-3">
                  <Label htmlFor="clear-from-out">Clear From Perimeter Pattern</Label>
                  <SearchableSelect
                    value={settings.custom_clear_from_out || '__default__'}
                    onValueChange={(value) =>
                      setSettings({ ...settings, custom_clear_from_out: value === '__default__' ? undefined : value })
                    }
                    options={[
                      { value: '__default__', label: 'Default (built-in)' },
                      ...patternFiles.map((file) => ({ value: file, label: file })),
                    ]}
                    placeholder="Default (built-in)"
                    searchPlaceholder="Search patterns..."
                    emptyMessage="No patterns found"
                  />
                  <p className="text-xs text-muted-foreground">
                    Pattern used when clearing from perimeter inward.
                  </p>
                </div>
              </div>
            </div>

            <Button
              onClick={handleSaveClearingSettings}
              disabled={isLoading === 'clearing'}
              className="gap-2"
            >
              {isLoading === 'clearing' ? (
                <span className="material-icons-outlined animate-spin">sync</span>
              ) : (
                <span className="material-icons-outlined">save</span>
              )}
              Save Clearing Settings
            </Button>
          </AccordionContent>
        </AccordionItem>

        {/* LED Controller Configuration */}
        <AccordionItem value="led" id="section-led" className="border rounded-lg px-4 overflow-visible bg-card">
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
              <div className="space-y-3 p-4 rounded-lg border">
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
              <div className="space-y-3 p-4 rounded-lg border">
                <Alert className="flex items-start">
                  <span className="material-icons-outlined text-base mr-2 shrink-0">info</span>
                  <AlertDescription>
                    Supports WS2812, WS2812B, SK6812 and other WS281x LED strips
                  </AlertDescription>
                </Alert>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-3">
                    <Label htmlFor="numLeds">Number of LEDs</Label>
                    <Input
                      id="numLeds"
                      type="text"
                      inputMode="numeric"
                      value={numLedsInput}
                      onChange={(e) => {
                        const val = e.target.value.replace(/[^0-9]/g, '')
                        setNumLedsInput(val)
                      }}
                      onBlur={() => {
                        const num = Math.min(1000, Math.max(1, parseInt(numLedsInput) || 60))
                        setLedConfig({ ...ledConfig, num_leds: num })
                        setNumLedsInput(String(num))
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          const num = Math.min(1000, Math.max(1, parseInt(numLedsInput) || 60))
                          setLedConfig({ ...ledConfig, num_leds: num })
                          setNumLedsInput(String(num))
                        }
                      }}
                    />
                  </div>
                  <div className="space-y-3">
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

                <div className="space-y-3">
                  <Label htmlFor="pixelOrder">Pixel Color Order</Label>
                  <Select
                    value={ledConfig.pixel_order || 'RGB'}
                    onValueChange={(value) =>
                      setLedConfig({ ...ledConfig, pixel_order: value })
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        <SelectLabel>RGB Strips (3-channel)</SelectLabel>
                        <SelectItem value="RGB">RGB - WS2815/WS2811</SelectItem>
                        <SelectItem value="GRB">GRB - WS2812/WS2812B</SelectItem>
                        <SelectItem value="BGR">BGR - Some WS2811 variants</SelectItem>
                        <SelectItem value="RBG">RBG - Rare variant</SelectItem>
                        <SelectItem value="GBR">GBR - Rare variant</SelectItem>
                        <SelectItem value="BRG">BRG - Rare variant</SelectItem>
                      </SelectGroup>
                      <SelectGroup>
                        <SelectLabel>RGBW Strips (4-channel)</SelectLabel>
                        <SelectItem value="GRBW">GRBW - SK6812 RGBW</SelectItem>
                        <SelectItem value="RGBW">RGBW - SK6812 variant</SelectItem>
                      </SelectGroup>
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
        <AccordionItem value="mqtt" id="section-mqtt" className="border rounded-lg px-4 overflow-visible bg-card">
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
            <div className="flex items-center justify-between p-4 rounded-lg border">
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
              <div className="space-y-3">
                {/* Broker Settings */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-3">
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
                  <div className="space-y-3">
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
                  <div className="space-y-3">
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
                  <div className="space-y-3">
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
                  <div className="space-y-3">
                    <Label htmlFor="mqttDeviceName">Device Name</Label>
                    <Input
                      id="mqttDeviceName"
                      value={mqttConfig.device_name || 'Dune Weaver'}
                      onChange={(e) =>
                        setMqttConfig({ ...mqttConfig, device_name: e.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-3">
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

            <div className="flex gap-3">
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
              {mqttConfig.enabled && mqttConfig.broker && (
                <Button
                  variant="secondary"
                  onClick={handleTestMqttConnection}
                  disabled={isLoading === 'mqttTest'}
                  className="gap-2"
                >
                  {isLoading === 'mqttTest' ? (
                    <span className="material-icons-outlined animate-spin">sync</span>
                  ) : (
                    <span className="material-icons-outlined">wifi_tethering</span>
                  )}
                  Test Connection
                </Button>
              )}
            </div>
          </AccordionContent>
        </AccordionItem>

        {/* Auto-play on Boot */}
        <AccordionItem value="autoplay" id="section-autoplay" className="border rounded-lg px-4 overflow-visible bg-card">
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
            <div className="flex items-center justify-between p-4 rounded-lg border">
              <div>
                <p className="font-medium">Enable Auto-play</p>
                <p className="text-sm text-muted-foreground">
                  Automatically start playing when the system boots
                </p>
              </div>
              <Switch
                checked={autoPlaySettings.enabled}
                onCheckedChange={(checked) =>
                  setAutoPlaySettings({ ...autoPlaySettings, enabled: checked })
                }
              />
            </div>

            {autoPlaySettings.enabled && (
              <div className="space-y-3 p-4 rounded-lg border">
                <div className="space-y-3">
                  <Label>Startup Playlist</Label>
                  <Select
                    value={autoPlaySettings.playlist || undefined}
                    onValueChange={(value) =>
                      setAutoPlaySettings({ ...autoPlaySettings, playlist: value })
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select a playlist..." />
                    </SelectTrigger>
                    <SelectContent>
                      {playlists.length === 0 ? (
                        <div className="py-6 text-center text-sm text-muted-foreground">
                          No playlists found
                        </div>
                      ) : (
                        playlists.map((playlist) => (
                          <SelectItem key={playlist} value={playlist}>
                            {playlist}
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    Choose which playlist to play when the system starts.
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-3">
                    <Label>Run Mode</Label>
                    <Select
                      value={autoPlaySettings.run_mode}
                      onValueChange={(value) =>
                        setAutoPlaySettings({
                          ...autoPlaySettings,
                          run_mode: value as 'single' | 'loop',
                        })
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="single">Single (play once)</SelectItem>
                        <SelectItem value="loop">Loop (repeat forever)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-3">
                    <Label>Pause Between Patterns</Label>
                    <div className="flex gap-2">
                      <Input
                        type="text"
                        inputMode="numeric"
                        value={autoPlayPauseInput}
                        onChange={(e) => {
                          const val = e.target.value.replace(/[^0-9]/g, '')
                          setAutoPlayPauseInput(val)
                        }}
                        onBlur={() => {
                          const num = Math.max(0, parseInt(autoPlayPauseInput) || 0)
                          setAutoPlayPauseValue(num)
                          setAutoPlayPauseInput(String(num))
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            const num = Math.max(0, parseInt(autoPlayPauseInput) || 0)
                            setAutoPlayPauseValue(num)
                            setAutoPlayPauseInput(String(num))
                          }
                        }}
                        className="w-20"
                      />
                      <Select
                        value={autoPlayPauseUnit}
                        onValueChange={(v) => setAutoPlayPauseUnit(v as 'sec' | 'min' | 'hr')}
                      >
                        <SelectTrigger className="w-20">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="sec">sec</SelectItem>
                          <SelectItem value="min">min</SelectItem>
                          <SelectItem value="hr">hr</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-3">
                    <Label>Clear Pattern</Label>
                    <Select
                      value={autoPlaySettings.clear_pattern}
                      onValueChange={(value) =>
                        setAutoPlaySettings({ ...autoPlaySettings, clear_pattern: value })
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">None</SelectItem>
                        <SelectItem value="adaptive">Adaptive</SelectItem>
                        <SelectItem value="clear_from_in">Clear From Center</SelectItem>
                        <SelectItem value="clear_from_out">Clear From Perimeter</SelectItem>
                        <SelectItem value="clear_sideway">Clear Sideway</SelectItem>
                        <SelectItem value="random">Random</SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      Pattern to run before each main pattern.
                    </p>
                  </div>

                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <p className="text-sm font-medium">Shuffle Playlist</p>
                      <p className="text-xs text-muted-foreground">
                        Randomize pattern order
                      </p>
                    </div>
                    <Switch
                      checked={autoPlaySettings.shuffle}
                      onCheckedChange={(checked) =>
                        setAutoPlaySettings({ ...autoPlaySettings, shuffle: checked })
                      }
                    />
                  </div>
                </div>
              </div>
            )}

            <Button
              onClick={handleSaveAutoPlaySettings}
              disabled={isLoading === 'autoplay'}
              className="gap-2"
            >
              {isLoading === 'autoplay' ? (
                <span className="material-icons-outlined animate-spin">sync</span>
              ) : (
                <span className="material-icons-outlined">save</span>
              )}
              Save Auto-play Settings
            </Button>
          </AccordionContent>
        </AccordionItem>

        {/* Still Sands */}
        <AccordionItem value="stillsands" id="section-stillsands" className="border rounded-lg px-4 overflow-visible bg-card">
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
            <div className="flex items-center justify-between p-4 rounded-lg border">
              <div>
                <p className="font-medium">Enable Still Sands</p>
                <p className="text-sm text-muted-foreground">
                  Pause the table during specified time periods
                </p>
              </div>
              <Switch
                checked={stillSandsSettings.enabled}
                onCheckedChange={(checked) =>
                  setStillSandsSettings({ ...stillSandsSettings, enabled: checked })
                }
              />
            </div>

            {stillSandsSettings.enabled && (
              <div className="space-y-3">
                {/* Options */}
                <div className="p-4 rounded-lg border space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="material-icons-outlined text-base text-muted-foreground">
                        hourglass_bottom
                      </span>
                      <div>
                        <p className="text-sm font-medium">Finish Current Pattern</p>
                        <p className="text-xs text-muted-foreground">
                          Let the current pattern complete before entering still mode
                        </p>
                      </div>
                    </div>
                    <Switch
                      checked={stillSandsSettings.finish_pattern}
                      onCheckedChange={(checked) =>
                        setStillSandsSettings({ ...stillSandsSettings, finish_pattern: checked })
                      }
                    />
                  </div>

                  <Separator />

                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="material-icons-outlined text-base text-muted-foreground">
                        lightbulb
                      </span>
                      <div>
                        <p className="text-sm font-medium">Control LED Lights</p>
                        <p className="text-xs text-muted-foreground">
                          Turn off LED lights during still periods
                        </p>
                      </div>
                    </div>
                    <Switch
                      checked={stillSandsSettings.control_wled}
                      onCheckedChange={(checked) =>
                        setStillSandsSettings({ ...stillSandsSettings, control_wled: checked })
                      }
                    />
                  </div>

                  {/* Timezone */}
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pt-3 border-t">
                    <div className="flex items-center gap-3">
                      <span className="material-icons-outlined text-muted-foreground">
                        schedule
                      </span>
                      <div>
                        <p className="text-sm font-medium">Timezone</p>
                        <p className="text-xs text-muted-foreground">
                          Select a timezone for scheduling
                        </p>
                      </div>
                    </div>
                    <SearchableSelect
                      value={stillSandsSettings.timezone || ''}
                      onValueChange={(value) =>
                        setStillSandsSettings({ ...stillSandsSettings, timezone: value })
                      }
                      placeholder="System Default"
                      searchPlaceholder="Search timezones..."
                      className="w-full sm:w-[200px]"
                      options={[
                        { value: '', label: 'System Default' },
                        { value: 'Etc/GMT+12', label: 'UTC-12' },
                        { value: 'Etc/GMT+11', label: 'UTC-11' },
                        { value: 'Etc/GMT+10', label: 'UTC-10' },
                        { value: 'Etc/GMT+9', label: 'UTC-9' },
                        { value: 'Etc/GMT+8', label: 'UTC-8' },
                        { value: 'Etc/GMT+7', label: 'UTC-7' },
                        { value: 'Etc/GMT+6', label: 'UTC-6' },
                        { value: 'Etc/GMT+5', label: 'UTC-5' },
                        { value: 'Etc/GMT+4', label: 'UTC-4' },
                        { value: 'Etc/GMT+3', label: 'UTC-3' },
                        { value: 'Etc/GMT+2', label: 'UTC-2' },
                        { value: 'Etc/GMT+1', label: 'UTC-1' },
                        { value: 'UTC', label: 'UTC' },
                        { value: 'Etc/GMT-1', label: 'UTC+1' },
                        { value: 'Etc/GMT-2', label: 'UTC+2' },
                        { value: 'Etc/GMT-3', label: 'UTC+3' },
                        { value: 'Etc/GMT-4', label: 'UTC+4' },
                        { value: 'Etc/GMT-5', label: 'UTC+5' },
                        { value: 'Etc/GMT-6', label: 'UTC+6' },
                        { value: 'Etc/GMT-7', label: 'UTC+7' },
                        { value: 'Etc/GMT-8', label: 'UTC+8' },
                        { value: 'Etc/GMT-9', label: 'UTC+9' },
                        { value: 'Etc/GMT-10', label: 'UTC+10' },
                        { value: 'Etc/GMT-11', label: 'UTC+11' },
                        { value: 'Etc/GMT-12', label: 'UTC+12' },
                        { value: 'America/New_York', label: 'America/New_York (Eastern)' },
                        { value: 'America/Chicago', label: 'America/Chicago (Central)' },
                        { value: 'America/Denver', label: 'America/Denver (Mountain)' },
                        { value: 'America/Los_Angeles', label: 'America/Los_Angeles (Pacific)' },
                        { value: 'Europe/London', label: 'Europe/London' },
                        { value: 'Europe/Paris', label: 'Europe/Paris' },
                        { value: 'Europe/Berlin', label: 'Europe/Berlin' },
                        { value: 'Asia/Tokyo', label: 'Asia/Tokyo' },
                        { value: 'Asia/Shanghai', label: 'Asia/Shanghai' },
                        { value: 'Asia/Singapore', label: 'Asia/Singapore' },
                        { value: 'Australia/Sydney', label: 'Australia/Sydney' },
                      ]}
                    />
                  </div>
                </div>

                {/* Time Slots */}
                <div className="p-4 rounded-lg border space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="font-medium">Still Periods</h4>
                    <Button onClick={addTimeSlot} size="sm" variant="secondary" className="gap-1">
                      <span className="material-icons text-base">add</span>
                      Add Period
                    </Button>
                  </div>

                  <p className="text-sm text-muted-foreground">
                    Define time periods when the sands should rest.
                  </p>

                  {stillSandsSettings.time_slots.length === 0 ? (
                    <div className="text-center py-6 text-muted-foreground">
                      <span className="material-icons text-3xl mb-2">schedule</span>
                      <p className="text-sm">No still periods configured</p>
                      <p className="text-xs">Click "Add Period" to create one</p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {stillSandsSettings.time_slots.map((slot, index) => (
                        <div
                          key={index}
                          className="p-3 border rounded-lg bg-muted/50 space-y-3 overflow-hidden"
                        >
                          <div className="flex items-center justify-between -mr-1">
                            <span className="text-sm font-medium">Period {index + 1}</span>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => removeTimeSlot(index)}
                              className="h-7 w-7 text-destructive hover:text-destructive"
                            >
                              <span className="material-icons text-lg">delete</span>
                            </Button>
                          </div>

                          <div className="grid grid-cols-2 gap-3">
                            <div className="space-y-1.5 min-w-0">
                              <Label className="text-xs">Start Time</Label>
                              <Input
                                type="time"
                                value={slot.start_time}
                                onChange={(e) =>
                                  updateTimeSlot(index, { start_time: e.target.value })
                                }
                                className="text-xs"
                              />
                            </div>
                            <div className="space-y-1.5 min-w-0">
                              <Label className="text-xs">End Time</Label>
                              <Input
                                type="time"
                                value={slot.end_time}
                                onChange={(e) =>
                                  updateTimeSlot(index, { end_time: e.target.value })
                                }
                                className="text-xs"
                              />
                            </div>
                          </div>

                          <div className="space-y-1.5">
                            <Label className="text-xs">Days</Label>
                            <Select
                              value={slot.days}
                              onValueChange={(value) =>
                                updateTimeSlot(index, {
                                  days: value as TimeSlot['days'],
                                })
                              }
                            >
                              <SelectTrigger>
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="daily">Daily</SelectItem>
                                <SelectItem value="weekdays">Weekdays</SelectItem>
                                <SelectItem value="weekends">Weekends</SelectItem>
                                <SelectItem value="custom">Custom</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <Alert className="flex items-start">
                  <span className="material-icons-outlined text-base mr-2 shrink-0">info</span>
                  <AlertDescription>
                    Times are based on the timezone selected above (or system default). Still
                    periods that span midnight (e.g., 22:00 to 06:00) are supported. Patterns
                    resume automatically when still periods end.
                  </AlertDescription>
                </Alert>
              </div>
            )}

            <Button
              onClick={handleSaveStillSandsSettings}
              disabled={isLoading === 'stillsands'}
              className="gap-2"
            >
              {isLoading === 'stillsands' ? (
                <span className="material-icons-outlined animate-spin">sync</span>
              ) : (
                <span className="material-icons-outlined">save</span>
              )}
              Save Still Sands Settings
            </Button>
          </AccordionContent>
        </AccordionItem>

        {/* Software Version */}
        <AccordionItem value="version" id="section-version" className="border rounded-lg px-4 overflow-visible bg-card">
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
          <AccordionContent className="pt-4 pb-6 space-y-3">
            <div className="flex items-center gap-4 p-4 rounded-lg bg-muted/50">
              <div className="w-10 h-10 flex items-center justify-center bg-background rounded-lg">
                <span className="material-icons text-muted-foreground">terminal</span>
              </div>
              <div className="flex-1">
                <p className="font-medium">Current Version</p>
                <p className="text-sm text-muted-foreground">
                  {versionInfo?.current ? `v${versionInfo.current}` : 'Loading...'}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-4 p-4 rounded-lg bg-muted/50">
              <div className="w-10 h-10 flex items-center justify-center bg-background rounded-lg">
                <span className="material-icons text-muted-foreground">system_update</span>
              </div>
              <div className="flex-1">
                <p className="font-medium">Latest Version</p>
                <p className={`text-sm ${versionInfo?.update_available ? 'text-green-600 dark:text-green-400 font-medium' : 'text-muted-foreground'}`}>
                  {versionInfo?.latest ? `v${versionInfo.latest}` : 'Checking...'}
                  {versionInfo?.update_available && ' (Update available!)'}
                </p>
              </div>
            </div>

            {versionInfo?.update_available && (
              <Alert className="flex items-start">
                <span className="material-icons-outlined text-base mr-2 shrink-0">info</span>
                <AlertDescription>
                  To update, run <code className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono">dw update</code> from the host machine.
                </AlertDescription>
              </Alert>
            )}
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  )
}
