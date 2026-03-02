import { useState, useEffect, useCallback } from 'react'
import { toast } from 'sonner'
import { apiClient } from '@/lib/apiClient'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'

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
  // Map signal percentage to a descriptive icon
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
  const [selectedNetwork, setSelectedNetwork] = useState<string | null>(null)
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

  const handleConnect = async () => {
    if (!selectedNetwork) return

    const network = networks.find(n => n.ssid === selectedNetwork)
    const needsPassword = network && network.security !== 'Open' && !network.saved

    setIsConnecting(true)
    try {
      const result = await apiClient.post<{ success: boolean; message: string }>('/api/wifi/connect', {
        ssid: selectedNetwork,
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

  const isHotspotMode = status?.mode === 'hotspot'

  const selectedNetworkData = networks.find(n => n.ssid === selectedNetwork)

  if (isRebooting) {
    return (
      <div className="container max-w-lg mx-auto px-4 py-8">
        <Card>
          <CardContent className="pt-6">
            <div className="text-center space-y-4">
              <span className="material-icons text-5xl text-blue-500 animate-spin">refresh</span>
              <h2 className="text-xl font-semibold">Rebooting...</h2>
              <p className="text-muted-foreground">
                The system is rebooting to connect to <strong>{selectedNetwork}</strong>.
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
    <div className="container max-w-lg mx-auto px-4 py-6 space-y-6">
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
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center gap-2">
            <span className="material-icons-outlined text-muted-foreground">info</span>
            WiFi Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          {status ? (
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-muted-foreground">Mode</p>
                <Badge variant={isHotspotMode ? 'secondary' : 'default'}>
                  {status.mode === 'hotspot' ? 'Hotspot' :
                   status.mode === 'client' ? 'Connected' : status.mode}
                </Badge>
              </div>
              {status.ssid && (
                <div>
                  <p className="text-muted-foreground">Network</p>
                  <p className="font-medium">{status.ssid}</p>
                </div>
              )}
              {status.ip && (
                <div>
                  <p className="text-muted-foreground">IP Address</p>
                  <p className="font-mono text-xs">{status.ip}</p>
                </div>
              )}
              <div>
                <p className="text-muted-foreground">Hostname</p>
                <p className="font-mono text-xs">{status.hostname}.local</p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Loading status...</p>
          )}
        </CardContent>
      </Card>

      {/* Available Networks */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-lg flex items-center gap-2">
                <span className="material-icons-outlined text-muted-foreground">wifi_find</span>
                Available Networks
              </CardTitle>
              <CardDescription>
                {networks.length > 0
                  ? `${networks.length} network${networks.length !== 1 ? 's' : ''} found`
                  : 'Scanning...'}
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={scanNetworks}
              disabled={isScanning}
            >
              <span className={`material-icons text-sm mr-1 ${isScanning ? 'animate-spin' : ''}`}>
                refresh
              </span>
              Scan
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-1">
          {networks.length === 0 && isScanning && (
            <p className="text-sm text-muted-foreground text-center py-4">
              Scanning for networks...
            </p>
          )}
          {networks.length === 0 && !isScanning && (
            <p className="text-sm text-muted-foreground text-center py-4">
              No networks found. Try scanning again.
            </p>
          )}
          {networks.map((network) => {
            const isSelected = selectedNetwork === network.ssid
            const showForm = isSelected && selectedNetworkData
            const showPasswordField = showForm &&
              selectedNetworkData.security !== 'Open' &&
              !selectedNetworkData.saved

            return (
              <div key={network.ssid}>
                <button
                  onClick={() => {
                    setSelectedNetwork(isSelected ? null : network.ssid)
                    setPassword('')
                    setShowPassword(false)
                  }}
                  className={`w-full flex items-center gap-3 p-3 rounded-lg text-left transition-colors
                    ${isSelected
                      ? 'bg-primary/10 ring-1 ring-primary'
                      : 'hover:bg-muted/50'
                    }
                    ${network.active ? 'bg-green-50 dark:bg-green-950/20' : ''}`}
                >
                  <SignalIcon signal={network.signal} />
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{network.ssid}</p>
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

                {/* Inline connection form — appears directly below selected network */}
                {showForm && (
                  <div className="mx-3 mb-2 mt-1 p-3 rounded-lg bg-muted/50 space-y-3">
                    {showPasswordField && (
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
                      disabled={isConnecting || (showPasswordField && !password)}
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
                )}
              </div>
            )
          })}
        </CardContent>
      </Card>

      {/* Saved Networks */}
      {savedConnections.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg flex items-center gap-2">
              <span className="material-icons-outlined text-muted-foreground">bookmark</span>
              Saved Networks
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {savedConnections.map((con) => (
              <div
                key={con.name}
                className="flex items-center justify-between p-3 rounded-lg hover:bg-muted/50"
              >
                <div className="flex items-center gap-3">
                  <span className="material-icons text-muted-foreground">wifi</span>
                  <span className="font-medium">{con.ssid}</span>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleForget(con.ssid)}
                  className="text-destructive hover:text-destructive"
                >
                  <span className="material-icons text-sm">delete</span>
                </Button>
              </div>
            ))}
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
    </div>
  )
}
