import { useState, useEffect, useCallback } from 'react'
import { toast } from 'sonner'
import { apiClient } from '@/lib/apiClient'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface WiFiNetwork {
  ssid: string
  signal: number
  security: string
  saved: boolean
  active: boolean
}

interface WiFiStatus {
  mode: string
  ssid: string
  ip: string
  hostname: string
}

interface SavedConnection {
  name: string
  ssid: string
}

function SignalIcon({ signal }: { signal: number }) {
  const bars = signal >= 75 ? 'signal_wifi_4_bar' :
               signal >= 50 ? 'network_wifi_3_bar' :
               signal >= 25 ? 'network_wifi_2_bar' :
               'network_wifi_1_bar'
  const color = signal >= 50 ? 'text-green-500' : signal >= 25 ? 'text-yellow-500' : 'text-red-500'
  return <span className={`material-icons text-lg ${color}`}>{bars}</span>
}

export function WiFiSetupPage() {
  const [status, setStatus] = useState<WiFiStatus | null>(null)
  const [networks, setNetworks] = useState<WiFiNetwork[]>([])
  const [savedConnections, setSavedConnections] = useState<SavedConnection[]>([])
  const [selectedNetwork, setSelectedNetwork] = useState<WiFiNetwork | null>(null)
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [isScanning, setIsScanning] = useState(false)
  const [isConnecting, setIsConnecting] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isManualEntry, setIsManualEntry] = useState(false)
  const [manualSsid, setManualSsid] = useState('')
  const [forgetSsid, setForgetSsid] = useState<string | null>(null)
  const [apPassword, setApPassword] = useState('')
  const [apPasswordInput, setApPasswordInput] = useState('')
  const [showApPassword, setShowApPassword] = useState(false)
  const [isSavingApPassword, setIsSavingApPassword] = useState(false)

  const fetchStatus = useCallback(async () => {
    try {
      const data = await apiClient.get<WiFiStatus>('/api/wifi/status')
      setStatus(data)
    } catch {
      // WiFi API may not be available (e.g., not on Pi)
    }
  }, [])

  const fetchSaved = useCallback(async () => {
    try {
      const data = await apiClient.get<SavedConnection[]>('/api/wifi/saved')
      setSavedConnections(data)
    } catch {
      // Silently fail
    }
  }, [])

  const fetchApPassword = useCallback(async () => {
    try {
      const data = await apiClient.get<{ password: string }>('/api/wifi/hotspot/password')
      setApPassword(data.password)
      setApPasswordInput(data.password)
    } catch {
      // Silently fail
    }
  }, [])

  const scanNetworks = useCallback(async () => {
    setIsScanning(true)
    try {
      const data = await apiClient.get<WiFiNetwork[]>('/api/wifi/networks')
      setNetworks(data)
    } catch {
      toast.error('Failed to scan networks')
    } finally {
      setIsScanning(false)
    }
  }, [])

  useEffect(() => {
    fetchStatus()
    scanNetworks()
    fetchSaved()
    fetchApPassword()
  }, [fetchStatus, scanNetworks, fetchSaved, fetchApPassword])

  const needsPassword = isManualEntry || (selectedNetwork &&
    selectedNetwork.security !== 'Open' &&
    !selectedNetwork.saved)

  const handleConnect = async () => {
    const ssid = isManualEntry ? manualSsid.trim() : selectedNetwork?.ssid
    if (!ssid) return

    setIsConnecting(true)
    try {
      const result = await apiClient.post<{ success: boolean; message: string }>('/api/wifi/connect', {
        ssid,
        password: needsPassword ? password : '',
      })

      if (result.success) {
        toast.success(result.message)
        closeDialog()
        fetchStatus()
        fetchSaved()
        scanNetworks()
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Connection failed'
      toast.error(message)
    } finally {
      setIsConnecting(false)
    }
  }

  const handleSave = async () => {
    const ssid = manualSsid.trim()
    if (!ssid) return

    setIsSaving(true)
    try {
      const result = await apiClient.post<{ success: boolean; message: string }>('/api/wifi/save', {
        ssid,
        password: password || '',
      })
      if (result.success) {
        toast.success(result.message)
        closeDialog()
        fetchSaved()
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save network'
      toast.error(message)
    } finally {
      setIsSaving(false)
    }
  }

  const handleForget = async () => {
    if (!forgetSsid) return
    const ssid = forgetSsid
    setForgetSsid(null)
    try {
      await apiClient.post('/api/wifi/forget', { ssid })
      toast.success(`Forgot '${ssid}'`)
      fetchSaved()
      scanNetworks()
    } catch {
      toast.error('Failed to forget network')
    }
  }

  const isForgetActive = forgetSsid === status?.ssid
  const otherSavedCount = savedConnections.filter(c => c.ssid !== forgetSsid).length
  const willStartHotspot = isForgetActive && otherSavedCount === 0

  const handleSaveApPassword = async () => {
    setIsSavingApPassword(true)
    try {
      const result = await apiClient.post<{ success: boolean; message: string }>('/api/wifi/hotspot/password', {
        password: apPasswordInput,
      })
      if (result.success) {
        setApPassword(apPasswordInput)
        toast.success(result.message)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update password'
      toast.error(message)
    } finally {
      setIsSavingApPassword(false)
    }
  }

  const openConnectDialog = (network: WiFiNetwork) => {
    setSelectedNetwork(network)
    setPassword('')
    setShowPassword(false)
  }

  const closeDialog = () => {
    if (!isConnecting && !isSaving) {
      setSelectedNetwork(null)
      setPassword('')
      setShowPassword(false)
      setIsManualEntry(false)
      setManualSsid('')
    }
  }

  const openManualEntry = () => {
    setIsManualEntry(true)
    setManualSsid('')
    setPassword('')
    setShowPassword(false)
    setSelectedNetwork({ ssid: '', signal: 0, security: 'Manual', saved: false, active: false })
  }

  const isHotspotMode = status?.mode === 'hotspot'

  return (
    <div className="container max-w-lg mx-auto px-3 py-4 space-y-3">
      {/* Hotspot Welcome Banner */}
      {isHotspotMode && (
        <Alert className="border-blue-200 bg-blue-50 dark:bg-blue-950/30 dark:border-blue-800">
          <span className="material-icons text-blue-500 mr-2">wifi_tethering</span>
          <AlertDescription>
            <strong>Welcome to Dune Weaver!</strong>
            <br />
            Connect to your home WiFi network below to get started.
          </AlertDescription>
        </Alert>
      )}

      {/* Current Status */}
      <Card>
        <CardContent className="pt-4 pb-3 px-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="material-icons-outlined text-base text-muted-foreground">info</span>
            <span className="font-semibold text-sm">WiFi Status</span>
          </div>
          {status ? (
            <div className="flex flex-wrap items-center justify-between gap-y-1 text-sm">
              <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
                <div className="flex items-center gap-1.5">
                  <span className="text-muted-foreground text-xs">Mode</span>
                  <Badge variant={isHotspotMode ? 'secondary' : 'default'} className="text-xs px-1.5 py-0">
                    {status.mode === 'hotspot' ? 'Hotspot' :
                     status.mode === 'client' ? 'Connected' : status.mode}
                  </Badge>
                </div>
                {status.ssid && (
                  <div className="flex items-center gap-1.5">
                    <span className="text-muted-foreground text-xs">Network</span>
                    <span className="font-medium text-xs">{status.ssid}</span>
                  </div>
                )}
                {status.ip && (
                  <div className="flex items-center gap-1.5">
                    <span className="text-muted-foreground text-xs">IP</span>
                    <span className="font-mono text-xs">{status.ip}</span>
                  </div>
                )}
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-muted-foreground text-xs">Host</span>
                <span className="font-mono text-xs">{status.hostname}.local</span>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Loading status...</p>
          )}
          {/* Raspberry Pi note */}
          {!isHotspotMode && (
            <p className="text-xs text-muted-foreground mt-2">
              WiFi management requires a Raspberry Pi.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Saved Networks */}
      {savedConnections.length > 0 && (
        <Card>
          <CardContent className="pt-4 pb-2 px-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="material-icons-outlined text-base text-muted-foreground">bookmark</span>
              <span className="font-semibold text-sm">Saved Networks</span>
            </div>
            <div className="space-y-0.5">
              {savedConnections.map((con) => (
                <div
                  key={con.name}
                  className="flex items-center justify-between px-2.5 py-2 rounded-lg hover:bg-muted/50"
                >
                  <div className="flex items-center gap-2.5">
                    <span className="material-icons text-muted-foreground text-lg">wifi</span>
                    <span className="font-medium text-sm">{con.ssid}</span>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0"
                    onClick={() => setForgetSsid(con.ssid)}
                  >
                    <span className="material-icons text-sm text-destructive">delete</span>
                  </Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Hotspot Password */}
      <Card>
        <CardContent className="pt-4 pb-3 px-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="material-icons-outlined text-base text-muted-foreground">wifi_tethering</span>
            <span className="font-semibold text-sm">Hotspot Password</span>
            {!apPassword && (
              <Badge variant="secondary" className="text-xs px-1.5 py-0">Open</Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground mb-3">
            Set a password for the Dune Weaver hotspot. Leave empty for an open network.
          </p>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Input
                type={showApPassword ? 'text' : 'password'}
                value={apPasswordInput}
                onChange={(e) => setApPasswordInput(e.target.value)}
                placeholder="No password (open)"
                className="pr-8 h-8 text-sm"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && apPasswordInput !== apPassword) handleSaveApPassword()
                }}
              />
              <button
                type="button"
                onClick={() => setShowApPassword(!showApPassword)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <span className="material-icons text-sm">
                  {showApPassword ? 'visibility_off' : 'visibility'}
                </span>
              </button>
            </div>
            <Button
              size="sm"
              className="h-8"
              onClick={handleSaveApPassword}
              disabled={isSavingApPassword || apPasswordInput === apPassword || (apPasswordInput.length > 0 && apPasswordInput.length < 8)}
            >
              {isSavingApPassword ? (
                <span className="material-icons text-sm animate-spin">refresh</span>
              ) : (
                'Save'
              )}
            </Button>
          </div>
          {apPasswordInput && apPasswordInput.length < 8 && apPasswordInput.length > 0 && (
            <p className="text-xs text-destructive mt-1">
              Password must be at least 8 characters
            </p>
          )}
        </CardContent>
      </Card>

      {/* Help */}
      {isHotspotMode && (
        <>
          <Separator />
          <div className="text-center text-sm text-muted-foreground space-y-1">
            <p>After connecting, access Dune Weaver at:</p>
            <code className="text-xs bg-muted px-2 py-1 rounded">
              http://{status?.hostname || 'duneweaver'}.local
            </code>
          </div>
        </>
      )}

      {/* System Controls */}
      <Card>
        <CardContent className="pt-4 pb-3 px-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="material-icons-outlined text-base text-muted-foreground">settings_power</span>
            <span className="font-semibold text-sm">System</span>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              className="flex-1 h-8"
              onClick={async () => {
                if (!confirm('Restart Dune Weaver?')) return
                try {
                  await apiClient.post('/api/system/restart')
                  toast.success('Restarting...')
                } catch { toast.error('Failed to restart') }
              }}
            >
              <span className="material-icons-outlined text-sm mr-1.5">restart_alt</span>
              Restart
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="flex-1 h-8 text-destructive hover:text-destructive"
              onClick={async () => {
                if (!confirm('Shutdown the system?')) return
                try {
                  await apiClient.post('/api/system/shutdown')
                  toast.success('Shutting down...')
                } catch { toast.error('Failed to shutdown') }
              }}
            >
              <span className="material-icons-outlined text-sm mr-1.5">power_settings_new</span>
              Shutdown
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Available Networks */}
      <Card>
        <CardContent className="pt-4 pb-2 px-4">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="material-icons-outlined text-base text-muted-foreground">wifi_find</span>
              <span className="font-semibold text-sm">Networks</span>
              <span className="text-xs text-muted-foreground">
                {networks.length > 0
                  ? `(${networks.length})`
                  : ''}
              </span>
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0"
                onClick={openManualEntry}
                title="Add network manually"
              >
                <span className="material-icons text-base">add</span>
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0"
                onClick={scanNetworks}
                disabled={isScanning}
              >
                <span className={`material-icons text-base ${isScanning ? 'animate-spin' : ''}`}>
                  refresh
                </span>
              </Button>
            </div>
          </div>
          <div className="space-y-0.5">
            {networks.length === 0 && isScanning && (
              <p className="text-sm text-muted-foreground text-center py-3">
                Scanning for networks...
              </p>
            )}
            {networks.length === 0 && !isScanning && (
              <p className="text-sm text-muted-foreground text-center py-3">
                No networks found. Try scanning again.
              </p>
            )}
            {networks.map((network) => (
              <button
                key={network.ssid}
                onClick={() => openConnectDialog(network)}
                className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left transition-colors hover:bg-muted/50
                  ${network.active ? 'bg-green-50 dark:bg-green-950/20' : ''}`}
              >
                <SignalIcon signal={network.signal} />
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm truncate">{network.ssid}</p>
                  <p className="text-xs text-muted-foreground">
                    {network.security}
                    {network.saved && ' · Saved'}
                    {network.active && ' · Connected'}
                  </p>
                </div>
                <span className="text-xs text-muted-foreground">{network.signal}%</span>
                {network.security !== 'Open' && (
                  <span className="material-icons text-sm text-muted-foreground">lock</span>
                )}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Forget Confirmation Dialog */}
      <Dialog open={forgetSsid !== null} onOpenChange={(open) => { if (!open) setForgetSsid(null) }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Forget '{forgetSsid}'?</DialogTitle>
            <DialogDescription>
              {willStartHotspot ? (
                <>
                  This is your only saved network. Forgetting it will start the
                  {' '}<strong>Dune Weaver</strong> hotspot. Connect to the Dune Weaver WiFi to access this page again.
                </>
              ) : isForgetActive ? (
                <>
                  You are currently connected to this network. The system will
                  try the next saved network, or start the hotspot if none are in range.
                </>
              ) : (
                'The saved credentials for this network will be removed.'
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="flex-row gap-2 sm:justify-end">
            <Button variant="outline" onClick={() => setForgetSsid(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleForget}>
              Forget
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Connect Dialog */}
      <Dialog open={selectedNetwork !== null} onOpenChange={(open) => { if (!open) closeDialog() }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {isManualEntry ? (
                <>
                  <span className="material-icons text-lg text-muted-foreground">add_circle_outline</span>
                  Add Network
                </>
              ) : (
                <>
                  {selectedNetwork && <SignalIcon signal={selectedNetwork.signal} />}
                  {selectedNetwork?.ssid}
                </>
              )}
            </DialogTitle>
            <DialogDescription>
              {isManualEntry
                ? 'Enter the network name and password'
                : <>
                    {selectedNetwork?.security !== 'Open' ? 'Secured network' : 'Open network'}
                    {selectedNetwork?.saved && ' · Saved'}
                  </>
              }
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {isManualEntry && (
              <div className="space-y-2">
                <Label htmlFor="wifi-ssid">Network Name (SSID)</Label>
                <Input
                  id="wifi-ssid"
                  type="text"
                  value={manualSsid}
                  onChange={(e) => setManualSsid(e.target.value)}
                  placeholder="Enter network name"
                  autoFocus
                />
              </div>
            )}

            {needsPassword && (
              <div className="space-y-2">
                <Label htmlFor="wifi-password">Password</Label>
                <div className="relative">
                  <Input
                    id="wifi-password"
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter WiFi password"
                    autoFocus={!isManualEntry}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && password) handleConnect()
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    <span className="material-icons text-sm">
                      {showPassword ? 'visibility_off' : 'visibility'}
                    </span>
                  </button>
                </div>
              </div>
            )}

            {isManualEntry ? (
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={handleSave}
                  disabled={isSaving || isConnecting || !manualSsid.trim() || (!!needsPassword && !password)}
                >
                  {isSaving ? (
                    <>
                      <span className="material-icons text-sm animate-spin mr-2">refresh</span>
                      Saving...
                    </>
                  ) : (
                    <>
                      <span className="material-icons text-sm mr-2">bookmark_add</span>
                      Save
                    </>
                  )}
                </Button>
                <Button
                  className="flex-1"
                  onClick={handleConnect}
                  disabled={isConnecting || isSaving || !manualSsid.trim() || (!!needsPassword && !password)}
                >
                  {isConnecting ? (
                    <>
                      <span className="material-icons text-sm animate-spin mr-2">refresh</span>
                      Connecting...
                    </>
                  ) : (
                    <>
                      <span className="material-icons text-sm mr-2">wifi</span>
                      Connect
                    </>
                  )}
                </Button>
              </div>
            ) : (
              <Button
                className="w-full"
                onClick={handleConnect}
                disabled={isConnecting || (!!needsPassword && !password)}
              >
                {isConnecting ? (
                  <>
                    <span className="material-icons text-sm animate-spin mr-2">refresh</span>
                    Connecting...
                  </>
                ) : (
                  <>
                    <span className="material-icons text-sm mr-2">wifi</span>
                    Connect
                  </>
                )}
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
