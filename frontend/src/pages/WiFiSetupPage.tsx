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
  const [isRebooting, setIsRebooting] = useState(false)

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
  }, [fetchStatus, scanNetworks, fetchSaved])

  const needsPassword = selectedNetwork &&
    selectedNetwork.security !== 'Open' &&
    !selectedNetwork.saved

  const handleConnect = async () => {
    if (!selectedNetwork) return

    setIsConnecting(true)
    try {
      const result = await apiClient.post<{ success: boolean; message: string }>('/api/wifi/connect', {
        ssid: selectedNetwork.ssid,
        password: needsPassword ? password : '',
      })

      if (result.success) {
        setIsRebooting(true)
        toast.success(result.message)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Connection failed'
      toast.error(message)
    } finally {
      setIsConnecting(false)
    }
  }

  const handleForget = async (ssid: string) => {
    try {
      await apiClient.post('/api/wifi/forget', { ssid })
      toast.success(`Forgot '${ssid}'`)
      fetchSaved()
      scanNetworks()
    } catch {
      toast.error('Failed to forget network')
    }
  }

  const openConnectDialog = (network: WiFiNetwork) => {
    setSelectedNetwork(network)
    setPassword('')
    setShowPassword(false)
  }

  const closeDialog = () => {
    if (!isConnecting) {
      setSelectedNetwork(null)
      setPassword('')
      setShowPassword(false)
    }
  }

  const isHotspotMode = status?.mode === 'hotspot'

  if (isRebooting) {
    return (
      <div className="container max-w-lg mx-auto px-4 py-8">
        <Card>
          <CardContent className="pt-6">
            <div className="text-center space-y-4">
              <span className="material-icons text-5xl text-blue-500 animate-spin">refresh</span>
              <h2 className="text-xl font-semibold">Rebooting...</h2>
              <p className="text-muted-foreground">
                The system is rebooting to connect to <strong>{selectedNetwork?.ssid}</strong>.
              </p>
              <p className="text-sm text-muted-foreground">
                Once connected, access Dune Weaver on your home network at:
              </p>
              <code className="text-sm bg-muted px-2 py-1 rounded">
                http://{status?.hostname || 'duneweaver'}.local
              </code>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

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
                    onClick={() => handleForget(con.ssid)}
                  >
                    <span className="material-icons text-sm text-destructive">delete</span>
                  </Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Help */}
      {isHotspotMode && (
        <>
          <Separator />
          <div className="text-center text-sm text-muted-foreground space-y-1">
            <p>After connecting, the system will reboot.</p>
            <p>Reconnect to your home WiFi and access Dune Weaver at:</p>
            <code className="text-xs bg-muted px-2 py-1 rounded">
              http://{status?.hostname || 'duneweaver'}.local
            </code>
          </div>
        </>
      )}

      {/* Connect Dialog */}
      <Dialog open={selectedNetwork !== null} onOpenChange={(open) => { if (!open) closeDialog() }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {selectedNetwork && <SignalIcon signal={selectedNetwork.signal} />}
              {selectedNetwork?.ssid}
            </DialogTitle>
            <DialogDescription>
              {selectedNetwork?.security !== 'Open' ? 'Secured network' : 'Open network'}
              {selectedNetwork?.saved && ' · Saved'}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
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
                    autoFocus
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
                  Connect{isHotspotMode ? ' & Reboot' : ''}
                </>
              )}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
