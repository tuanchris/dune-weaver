import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
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
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { SearchableSelect } from '@/components/ui/searchable-select'
import { UpdateDialog } from '@/components/UpdateDialog'

// Types

interface Settings {
  app_name?: string
  custom_logo?: string
  // Homing settings
  homing_mode?: number
  angular_offset?: number
  home_on_connect?: boolean
  auto_home_enabled?: boolean
  auto_home_after_patterns?: number
  hard_reset_theta?: boolean
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

// Auto-play on boot lives on the board ($Playlist/Autostart*): it fires when
// the table powers on and homes, independent of this backend. enabled is
// derived from a non-empty playlist, like the mobile app.
interface AutoPlaySettings {
  enabled: boolean
  playlist: string
  run_mode: 'single' | 'loop'
  pause_time: number
  pause_from_start: boolean
  clear_pattern: string
  shuffle: boolean
}

interface BoardTime {
  epoch: number
  synced: boolean
  local: string
  tz: string
}

interface LedConfig {
  provider: 'none' | 'wled' | 'board'
  wled_ip?: string
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
  const navigate = useNavigate()
  const sectionParam = searchParams.get('section')

  // Connection state — the board is reached over HTTP (FluidNC firmware),
  // identified by an IP or hostname instead of a serial port.
  const [boardAddress, setBoardAddress] = useState('')
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

  // Auto-play state (read from / written to the board)
  const [autoPlaySettings, setAutoPlaySettings] = useState<AutoPlaySettings>({
    enabled: false,
    playlist: '',
    run_mode: 'loop',
    pause_time: 0,
    pause_from_start: false,
    clear_pattern: 'none',
    shuffle: false,
  })
  const [boardReachable, setBoardReachable] = useState(true)
  const [boardTime, setBoardTime] = useState<BoardTime | null>(null)
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

  // Security state
  const [securityMode, setSecurityMode] = useState<'off' | 'lockdown' | 'play_only'>('off')
  const [securityPassword, setSecurityPassword] = useState('')
  const [securityPasswordConfirm, setSecurityPasswordConfirm] = useState('')
  const [hasExistingPassword, setHasExistingPassword] = useState(false)

  // Version state
  const [versionInfo, setVersionInfo] = useState<{
    current: string
    latest: string
    update_available: boolean
  } | null>(null)
  const [updateDialogOpen, setUpdateDialogOpen] = useState(false)

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
        await fetchConnection()
        if (!loadedSections.has('_settings')) {
          setLoadedSections((prev) => new Set(prev).add('_settings'))
          await fetchSettings()
        }
        break
      case 'application':
      case 'mqtt':
      case 'autoplay':
      case 'stillsands':
      case 'homing':
      case 'clearing':
      case 'security':
        // These all share settings data
        if (!loadedSections.has('_settings')) {
          setLoadedSections((prev) => new Set(prev).add('_settings'))
          await fetchSettings()
        }
        if ((section === 'autoplay' || section === 'clearing') && !loadedSections.has('_playlists')) {
          setLoadedSections((prev) => new Set(prev).add('_playlists'))
          await fetchPlaylists()
        }
        if ((section === 'autoplay' || section === 'stillsands') && !loadedSections.has('_board')) {
          setLoadedSections((prev) => new Set(prev).add('_board'))
          await fetchBoardSettings()
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

  const fetchConnection = async () => {
    try {
      // The backend reports the configured board URL as the single "port".
      const statusData = await apiClient.get<{ connected: boolean; port?: string }>('/serial_status')
      setIsConnected(statusData.connected || false)
      setConnectionStatus(
        statusData.connected ? `Connected to ${statusData.port || 'board'}` : 'Disconnected'
      )
      if (statusData.port) {
        setBoardAddress((prev) => prev || statusData.port || '')
      } else {
        const urls = await apiClient.get<string[]>('/list_serial_ports')
        if (urls?.[0]) setBoardAddress((prev) => prev || urls[0])
      }
    } catch (error) {
      console.error('Error fetching connection status:', error)
    }
  }

  // Always fetch connection state on mount since connection is the default section
  useEffect(() => {
    fetchConnection()
  }, [])

  // Refetch when backend reconnects
  useOnBackendConnected(() => {
    fetchConnection()
  })

  const fetchSettings = async () => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const data = await apiClient.get<Record<string, any>>('/api/settings')
      // Map the nested API response to our flat Settings interface
      setSettings({
        app_name: data.app?.name,
        custom_logo: data.app?.custom_logo,
        // Homing settings
        homing_mode: data.homing?.mode,
        angular_offset: data.homing?.angular_offset_degrees,
        home_on_connect: data.homing?.home_on_connect,
        auto_home_enabled: data.homing?.auto_home_enabled,
        auto_home_after_patterns: data.homing?.auto_home_after_patterns,
        hard_reset_theta: data.homing?.hard_reset_theta,
        // Pattern clearing settings
        clear_pattern_speed: data.patterns?.clear_pattern_speed,
        custom_clear_from_in: data.patterns?.custom_clear_from_in,
        custom_clear_from_out: data.patterns?.custom_clear_from_out,
      })
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
      // Set security settings
      if (data.security) {
        setSecurityMode(data.security.mode || 'off')
        setHasExistingPassword(data.security.has_password || false)
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
      })
    } catch (error) {
      console.error('Error fetching LED config:', error)
    }
  }

  const fetchBoardSettings = async () => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const data = await apiClient.get<Record<string, any>>('/api/board/settings')
      setBoardReachable(!!data.reachable)
      if (!data.reachable) return
      if (data.time) setBoardTime(data.time)
      if (data.autostart) {
        const a = data.autostart
        const pauseSeconds = a.pause_seconds ?? 0
        const { value, unit } = secondsToDisplayPause(pauseSeconds)
        setAutoPlayPauseValue(value)
        setAutoPlayPauseInput(String(value))
        setAutoPlayPauseUnit(unit)
        setAutoPlaySettings({
          enabled: !!a.playlist,
          playlist: a.playlist || '',
          run_mode: a.run_mode === 'single' ? 'single' : 'loop',
          pause_time: pauseSeconds,
          pause_from_start: !!a.pause_from_start,
          clear_pattern: a.clear_pattern || 'none',
          shuffle: !!a.shuffle,
        })
      }
    } catch (error) {
      console.error('Error fetching board settings:', error)
      setBoardReachable(false)
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
    if (!boardAddress.trim()) {
      toast.error('Enter the table IP or hostname')
      return
    }
    setIsLoading('connect')
    try {
      const data = await apiClient.post<{ success?: boolean; message?: string }>('/connect', { port: boardAddress.trim() })
      if (data.success) {
        setIsConnected(true)
        setConnectionStatus(`Connected to ${boardAddress.trim()}`)
        toast.success('Connected to the table')
      } else {
        throw new Error(data.message || 'Connection failed')
      }
    } catch (error) {
      toast.error('Could not reach the table at that address')
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
      await apiClient.post('/set_led_config', {
        provider: ledConfig.provider,
        ip_address: ledConfig.wled_ip,
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

  const handleSaveHomingConfig = async () => {
    setIsLoading('homing')
    try {
      await apiClient.patch('/api/settings', {
        homing: {
          mode: settings.homing_mode,
          angular_offset_degrees: settings.angular_offset,
          home_on_connect: settings.home_on_connect,
          auto_home_enabled: settings.auto_home_enabled,
          auto_home_after_patterns: settings.auto_home_after_patterns,
          hard_reset_theta: settings.hard_reset_theta,
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
    if (autoPlaySettings.enabled && !autoPlaySettings.playlist) {
      toast.error('Choose a startup playlist first')
      return
    }
    setIsLoading('autoplay')
    try {
      const pauseTimeSeconds = displayPauseToSeconds(autoPlayPauseValue, autoPlayPauseUnit)
      // Stored on the board: an empty playlist disables auto-play on boot.
      await apiClient.patch('/api/board/settings', {
        autostart: {
          playlist: autoPlaySettings.enabled ? autoPlaySettings.playlist : '',
          run_mode: autoPlaySettings.run_mode,
          shuffle: autoPlaySettings.shuffle,
          pause_seconds: pauseTimeSeconds,
          pause_from_start: autoPlaySettings.pause_from_start,
          clear_pattern: autoPlaySettings.clear_pattern,
        },
      })
      toast.success('Auto-play saved to the table')
    } catch (error) {
      toast.error('Could not save — is the table connected?')
    } finally {
      setIsLoading(null)
    }
  }

  const handleSaveStillSandsSettings = async () => {
    setIsLoading('stillsands')
    try {
      // The backend also pushes these to the table's own quiet-hours settings
      // ($Sands/*), so playlists started on the table honor the same schedule.
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

  const handleSyncBoardTime = async () => {
    setIsLoading('synctime')
    try {
      const data = await apiClient.post<{ success: boolean; time?: BoardTime }>('/api/board/sync_time')
      if (data.time) setBoardTime(data.time)
      toast.success('Table clock synced')
    } catch (error) {
      toast.error('Could not sync the table clock')
    } finally {
      setIsLoading(null)
    }
  }

  const addTimeSlot = () => {
    setStillSandsSettings({
      ...stillSandsSettings,
      time_slots: [
        ...stillSandsSettings.time_slots,
        { start_time: '22:00', end_time: '06:00', days: 'daily', custom_days: [] },
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
        {/* Table Connection */}
        <AccordionItem value="connection" id="section-connection" className="border rounded-lg px-4 overflow-visible bg-card">
          <AccordionTrigger className="hover:no-underline">
            <div className="flex items-center gap-3">
              <span className="material-icons-outlined text-muted-foreground">
                wifi
              </span>
              <div className="text-left">
                <div className="font-semibold">Table Connection</div>
                <div className="text-sm text-muted-foreground font-normal">
                  Controller board address
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
                    {isConnected ? 'wifi' : 'wifi_off'}
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

            {/* Board address */}
            <div className="space-y-3">
              <Label htmlFor="board-address">Table address</Label>
              <div className="flex gap-3">
                <Input
                  id="board-address"
                  value={boardAddress}
                  onChange={(e) => setBoardAddress(e.target.value)}
                  placeholder="IP or host (e.g. 192.168.68.160)"
                  autoCapitalize="none"
                  autoCorrect="off"
                  className="flex-1"
                />
                <Button
                  onClick={handleConnect}
                  disabled={isLoading === 'connect' || !boardAddress.trim()}
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
                The FluidNC controller inside the table, on the same network as this server.
                The address is saved and reconnected automatically on startup.
              </p>
            </div>

            {/* Home on Connect */}
            <div className="p-4 rounded-lg border space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium flex items-center gap-2">
                    <span className="material-icons-outlined text-base">power</span>
                    Home on Connect
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Automatically home when connecting on startup. Disable to connect without homing and home manually later.
                  </p>
                </div>
                <Switch
                  checked={settings.home_on_connect !== false}
                  onCheckedChange={async (checked) => {
                    setSettings({ ...settings, home_on_connect: checked })
                    try {
                      await apiClient.patch('/api/settings', {
                        homing: { home_on_connect: checked },
                      })
                      toast.success(checked ? 'Home on connect enabled' : 'Home on connect disabled')
                    } catch {
                      toast.error('Failed to save setting')
                    }
                  }}
                />
              </div>
            </div>
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

            {/* Machine Reset on Theta Normalization */}
            <div className="p-4 rounded-lg border space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium flex items-center gap-2">
                    <span className="material-icons-outlined text-base">restart_alt</span>
                    Reset Machine on Theta Normalization
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Also reset the machine controller when normalizing theta
                  </p>
                </div>
                <Switch
                  checked={settings.hard_reset_theta || false}
                  onCheckedChange={(checked) =>
                    setSettings({ ...settings, hard_reset_theta: checked })
                  }
                />
              </div>
              <p className="text-xs text-muted-foreground">
                When disabled (default), theta normalization only adjusts the angle mathematically.
                When enabled, also resets the machine controller to clear position counters.
              </p>
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
                  Table LEDs or WLED control
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
                  <RadioGroupItem value="board" id="led-board" />
                  <Label htmlFor="led-board" className="font-normal">Table LEDs (built-in)</Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="wled" id="led-wled" />
                  <Label htmlFor="led-wled" className="font-normal">WLED</Label>
                </div>
              </RadioGroup>
            </div>

            {/* Board LEDs info */}
            {ledConfig.provider === 'board' && (
              <div className="space-y-3 p-4 rounded-lg border">
                <Alert className="flex items-start">
                  <span className="material-icons-outlined text-base mr-2 shrink-0">info</span>
                  <AlertDescription>
                    The LED ring wired to the table's controller board, driven by the
                    firmware. Effects, colors and brightness are controlled from the
                    LED page and persist on the table itself.
                  </AlertDescription>
                </Alert>
              </div>
            )}

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

            <div className="flex flex-wrap gap-3">
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
                  Start a playlist when the table powers on
                </div>
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent className="pt-4 pb-6 space-y-6">
            {!boardReachable && (
              <Alert>
                <AlertDescription>
                  The table is not reachable, so its saved auto-play settings can't be shown.
                  Connect to the table first (Table Connection above).
                </AlertDescription>
              </Alert>
            )}
            <div className="flex items-center justify-between p-4 rounded-lg border">
              <div>
                <p className="font-medium">Enable Auto-play</p>
                <p className="text-sm text-muted-foreground">
                  Automatically start a playlist after the table powers on and homes.
                  Stored on the table, so it works even when this server is off.
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
                        <SelectItem value="in">Clear From Center</SelectItem>
                        <SelectItem value="out">Clear From Perimeter</SelectItem>
                        <SelectItem value="sideway">Clear Sideways</SelectItem>
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

                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <p className="text-sm font-medium">Pause From Start</p>
                    <p className="text-xs text-muted-foreground">
                      Measure the gap from each pattern's start, not its end
                    </p>
                  </div>
                  <Switch
                    checked={autoPlaySettings.pause_from_start}
                    onCheckedChange={(checked) =>
                      setAutoPlaySettings({ ...autoPlaySettings, pause_from_start: checked })
                    }
                  />
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
            {/* Table clock — quiet hours only fire on the table when its clock is set */}
            <div className="flex items-center justify-between p-4 rounded-lg border">
              <div className="flex items-center gap-3">
                <span className="material-icons-outlined text-muted-foreground">schedule</span>
                <div>
                  <p className="font-medium">Table Clock</p>
                  <p className="text-sm text-muted-foreground">
                    {boardTime
                      ? `${boardTime.local || '—'} · ${boardTime.tz || 'no timezone'} · ${boardTime.synced ? 'synced' : 'not set'}`
                      : 'No clock reported — is the table connected?'}
                  </p>
                  {boardTime && !boardTime.synced && (
                    <p className="text-xs text-destructive mt-1">
                      The table clock isn't set, so schedules won't fire on the table.
                      The server syncs it on connect — sync now to set it immediately.
                    </p>
                  )}
                </div>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={handleSyncBoardTime}
                disabled={isLoading === 'synctime'}
                className="gap-2"
              >
                {isLoading === 'synctime' ? (
                  <span className="material-icons-outlined animate-spin text-base">sync</span>
                ) : (
                  <span className="material-icons-outlined text-base">sync</span>
                )}
                Sync
              </Button>
            </div>

            <div className="flex items-center justify-between p-4 rounded-lg border">
              <div>
                <p className="font-medium">Enable Still Sands</p>
                <p className="text-sm text-muted-foreground">
                  Pause the table during scheduled quiet periods. Shared with the
                  table itself, so playlists started from a phone stay quiet too.
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
                        <p className="text-sm font-medium">Turn Off LEDs</p>
                        <p className="text-xs text-muted-foreground">
                          Switch off the lights during still periods (WLED and the table's LED ring)
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

                          <div className="grid grid-cols-[1fr_1fr] gap-2">
                            <div className="space-y-1.5 min-w-0 overflow-hidden">
                              <Label className="text-xs">Start Time</Label>
                              <Input
                                type="time"
                                value={slot.start_time}
                                onChange={(e) =>
                                  updateTimeSlot(index, { start_time: e.target.value })
                                }
                                className="text-xs w-full"
                              />
                            </div>
                            <div className="space-y-1.5 min-w-0 overflow-hidden">
                              <Label className="text-xs">End Time</Label>
                              <Input
                                type="time"
                                value={slot.end_time}
                                onChange={(e) =>
                                  updateTimeSlot(index, { end_time: e.target.value })
                                }
                                className="text-xs w-full"
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
                                  ...(value !== 'custom' ? { custom_days: [] } : {}),
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

                          {slot.days === 'custom' && (
                            <div className="space-y-1.5">
                              <Label className="text-xs">Select Days</Label>
                              <div className="flex flex-wrap gap-1.5">
                                {[
                                  { key: 'monday', label: 'Mon' },
                                  { key: 'tuesday', label: 'Tue' },
                                  { key: 'wednesday', label: 'Wed' },
                                  { key: 'thursday', label: 'Thu' },
                                  { key: 'friday', label: 'Fri' },
                                  { key: 'saturday', label: 'Sat' },
                                  { key: 'sunday', label: 'Sun' },
                                ].map((day) => {
                                  const isSelected = slot.custom_days?.includes(day.key)
                                  return (
                                    <button
                                      key={day.key}
                                      type="button"
                                      onClick={() => {
                                        const currentDays = slot.custom_days || []
                                        const newDays = isSelected
                                          ? currentDays.filter((d) => d !== day.key)
                                          : [...currentDays, day.key]
                                        updateTimeSlot(index, { custom_days: newDays })
                                      }}
                                      className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${
                                        isSelected
                                          ? 'bg-primary text-primary-foreground border-primary'
                                          : 'bg-background text-muted-foreground border-input hover:bg-accent'
                                      }`}
                                    >
                                      {day.label}
                                    </button>
                                  )
                                })}
                              </div>
                            </div>
                          )}
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

        {/* Security */}
        <AccordionItem value="security" id="section-security" className="border rounded-lg px-4 overflow-visible bg-card">
          <AccordionTrigger className="hover:no-underline">
            <div className="flex items-center gap-3">
              <span className="material-icons-outlined text-muted-foreground">
                lock
              </span>
              <div className="text-left">
                <div className="font-semibold">Security</div>
                <div className="text-sm text-muted-foreground font-normal">
                  App lock and access control
                </div>
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent className="pt-4 pb-6 space-y-4">
            <p className="text-sm text-muted-foreground">
              Restrict access to the app to prevent unauthorized changes. Useful for shared spaces or when the table is accessible to children.
            </p>

            {/* Security Mode */}
            <div className="space-y-3">
              <Label className="text-sm font-medium">Security Mode</Label>
              <RadioGroup
                value={securityMode}
                onValueChange={(value) => {
                  const newMode = value as 'off' | 'lockdown' | 'play_only'
                  if (newMode === 'off' && securityMode !== 'off') {
                    if (!confirm('Turn off security? This will remove the password and unlock the app.')) return
                  }
                  setSecurityMode(newMode)
                  // Clear password fields when switching modes
                  setSecurityPassword('')
                  setSecurityPasswordConfirm('')
                }}
                className="space-y-2"
              >
                <div className="flex items-start gap-3 p-3 rounded-lg border">
                  <RadioGroupItem value="off" id="security-off" className="mt-0.5" />
                  <div>
                    <Label htmlFor="security-off" className="font-medium cursor-pointer">Off</Label>
                    <p className="text-sm text-muted-foreground">No restrictions. Anyone can use the app.</p>
                  </div>
                </div>
                <div className="flex items-start gap-3 p-3 rounded-lg border">
                  <RadioGroupItem value="play_only" id="security-play-only" className="mt-0.5" />
                  <div>
                    <Label htmlFor="security-play-only" className="font-medium cursor-pointer">Play Only</Label>
                    <p className="text-sm text-muted-foreground">Anyone can browse and play patterns. Settings require a password.</p>
                  </div>
                </div>
                <div className="flex items-start gap-3 p-3 rounded-lg border">
                  <RadioGroupItem value="lockdown" id="security-lockdown" className="mt-0.5" />
                  <div>
                    <Label htmlFor="security-lockdown" className="font-medium cursor-pointer">Full Lockdown</Label>
                    <p className="text-sm text-muted-foreground">Password required to access the entire app.</p>
                  </div>
                </div>
              </RadioGroup>
            </div>

            {/* Password fields (shown when mode != off) */}
            {securityMode !== 'off' && (
              <div className="space-y-3 pt-2">
                <Separator />
                {hasExistingPassword && (
                  <p className="text-sm text-muted-foreground">
                    A password is currently set. Enter a new password below to change it, or leave blank to keep the existing one.
                  </p>
                )}
                <div className="space-y-2">
                  <Label htmlFor="security-password">
                    {hasExistingPassword ? 'New Password' : 'Password'}
                  </Label>
                  <Input
                    id="security-password"
                    type="password"
                    placeholder={hasExistingPassword ? 'Leave blank to keep current' : 'Enter password'}
                    value={securityPassword}
                    onChange={(e) => setSecurityPassword(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="security-password-confirm">Confirm Password</Label>
                  <Input
                    id="security-password-confirm"
                    type="password"
                    placeholder="Confirm password"
                    value={securityPasswordConfirm}
                    onChange={(e) => setSecurityPasswordConfirm(e.target.value)}
                  />
                </div>
                {securityPassword && securityPasswordConfirm && securityPassword !== securityPasswordConfirm && (
                  <p className="text-sm text-destructive">Passwords do not match</p>
                )}
              </div>
            )}

            {/* Save button */}
            <Button
              onClick={async () => {
                // Validate
                if (securityMode !== 'off') {
                  if (securityPassword && securityPassword !== securityPasswordConfirm) {
                    toast.error('Passwords do not match')
                    return
                  }
                  if (!hasExistingPassword && !securityPassword) {
                    toast.error('Please set a password')
                    return
                  }
                }

                setIsLoading('security')
                try {
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  const payload: any = { security: { mode: securityMode } }
                  if (securityPassword) {
                    payload.security.password = securityPassword
                  }
                  await apiClient.patch('/api/settings', payload)
                  toast.success('Security settings saved')
                  setSecurityPassword('')
                  setSecurityPasswordConfirm('')
                  setHasExistingPassword(securityMode !== 'off')
                  // Notify Layout to refetch security state
                  window.dispatchEvent(new CustomEvent('security-updated'))
                } catch {
                  toast.error('Failed to save security settings')
                } finally {
                  setIsLoading(null)
                }
              }}
              disabled={
                isLoading === 'security' ||
                (securityMode !== 'off' && securityPassword !== '' && securityPassword !== securityPasswordConfirm) ||
                (securityMode !== 'off' && !hasExistingPassword && !securityPassword)
              }
              className="w-full gap-2"
            >
              {isLoading === 'security' ? (
                <span className="material-icons-outlined animate-spin">sync</span>
              ) : (
                <span className="material-icons-outlined">save</span>
              )}
              Save Security Settings
            </Button>
          </AccordionContent>
        </AccordionItem>

        {/* WiFi */}
        <AccordionItem value="wifi" id="section-wifi" className="border rounded-lg px-4 overflow-visible bg-card">
          <AccordionTrigger className="hover:no-underline">
            <div className="flex items-center gap-3">
              <span className="material-icons-outlined text-muted-foreground">
                wifi
              </span>
              <div className="text-left">
                <div className="font-semibold">WiFi</div>
                <div className="text-sm text-muted-foreground font-normal">
                  Network connection settings
                </div>
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent className="pt-4 pb-6 space-y-3">
            <p className="text-sm text-muted-foreground">
              Manage WiFi connections, scan for networks, and configure hotspot mode.
            </p>
            <Button
              variant="outline"
              className="w-full gap-2"
              onClick={() => navigate('/wifi-setup')}
            >
              <span className="material-icons-outlined">settings</span>
              Open WiFi Setup
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
                  {versionInfo?.latest ? (
                    <a
                      href={`https://github.com/tuanchris/dune-weaver/releases/tag/v${versionInfo.latest}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="underline underline-offset-2 hover:opacity-80 transition-opacity"
                    >
                      v{versionInfo.latest}
                    </a>
                  ) : 'Checking...'}
                  {versionInfo?.update_available && ' (Update available!)'}
                </p>
              </div>
            </div>

            {versionInfo?.update_available && (
              <Button onClick={() => setUpdateDialogOpen(true)} className="w-full">
                <span className="material-icons text-base mr-2">system_update</span>
                Update Now
              </Button>
            )}

            <UpdateDialog
              open={updateDialogOpen}
              onOpenChange={setUpdateDialogOpen}
              currentVersion={versionInfo?.current || ''}
              latestVersion={versionInfo?.latest || ''}
            />
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  )
}
