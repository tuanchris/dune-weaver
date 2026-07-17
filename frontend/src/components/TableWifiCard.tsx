import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { apiClient } from '@/lib/apiClient'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface WifiStatus {
  supported: boolean
  mode?: 'sta' | 'fallback' | 'standalone'
  sta_ssid?: string
  ap_ssid?: string
  fail?: string
}

interface WifiNetwork {
  ssid: string
  rssi: number
  secure: number | boolean
}

const MODE_LABELS: Record<string, string> = {
  sta: 'On home Wi-Fi',
  fallback: 'Setup hotspot (could not join home Wi-Fi)',
  standalone: 'Standalone hotspot',
}

/**
 * Manage the FluidNC board's own Wi-Fi (fw >= v0.1.8) — distinct from the
 * host's Wi-Fi setup page. Moving the table to a new network reboots it; the
 * backend's mDNS relocate watchdog re-finds it afterwards.
 */
export function TableWifiCard({ isConnected }: { isConnected: boolean }) {
  const [status, setStatus] = useState<WifiStatus | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [networks, setNetworks] = useState<WifiNetwork[]>([])
  const [selectedSsid, setSelectedSsid] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const scanTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const fetchStatus = async () => {
    try {
      const data = await apiClient.get<WifiStatus>('/api/board/wifi/status')
      setStatus(data)
    } catch {
      setStatus(null)
    }
  }

  useEffect(() => {
    if (isConnected) fetchStatus()
    return () => {
      if (scanTimer.current) clearTimeout(scanTimer.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isConnected])

  const pollScan = async (rescan: boolean) => {
    try {
      const data = await apiClient.get<{ status: string; aps?: WifiNetwork[] }>(
        `/api/board/wifi/scan${rescan ? '?rescan=true' : ''}`
      )
      if (data.status === 'ok') {
        setScanning(false)
        setNetworks(
          (data.aps || [])
            .filter((a) => a.ssid)
            .sort((a, b) => b.rssi - a.rssi)
        )
      } else {
        scanTimer.current = setTimeout(() => pollScan(false), 2000)
      }
    } catch {
      setScanning(false)
      toast.error('Wi-Fi scan failed')
    }
  }

  const startScan = () => {
    setScanning(true)
    setNetworks([])
    pollScan(true)
  }

  const joinNetwork = async () => {
    if (!selectedSsid || password.length < 8) return
    setBusy('join')
    try {
      const data = await apiClient.post<{ success?: boolean; rebooting?: boolean }>(
        '/api/board/wifi/save',
        { ssid: selectedSsid, password }
      )
      if (data.rebooting) {
        toast.success(
          `Table is rebooting onto "${selectedSsid}". If its address changes, it will be re-found automatically.`,
          { duration: 8000 }
        )
      } else {
        toast.success(`Table joined "${selectedSsid}"`)
      }
      setExpanded(false)
      setPassword('')
      setSelectedSsid('')
    } catch (e) {
      const msg = e instanceof Error ? e.message : ''
      toast.error(
        msg.includes('busy')
          ? 'The table is busy - stop the current pattern first'
          : 'The table rejected those credentials'
      )
    } finally {
      setBusy(null)
    }
  }

  const switchToStandalone = async () => {
    if (
      !window.confirm(
        'Switch the table to standalone hotspot mode? It will LEAVE this network and broadcast its own Wi-Fi - this server will lose the connection until the table is back on the same network.'
      )
    ) {
      return
    }
    setBusy('standalone')
    try {
      await apiClient.post('/api/board/wifi/standalone')
      toast.success('Table is switching to hotspot mode and leaving this network', {
        duration: 8000,
      })
    } catch {
      toast.error('Could not switch to standalone mode')
    } finally {
      setBusy(null)
    }
  }

  if (!isConnected || !status) return null
  if (!status.supported) return null

  return (
    <div className="p-4 rounded-lg border space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="font-medium flex items-center gap-2">
            <span className="material-icons-outlined text-base">router</span>
            Table Wi-Fi
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            {MODE_LABELS[status.mode || ''] || 'Unknown mode'}
            {status.mode === 'sta' && status.sta_ssid ? ` - "${status.sta_ssid}"` : ''}
            {status.mode !== 'sta' && status.ap_ssid ? ` - "${status.ap_ssid}"` : ''}
            {status.fail ? ` (join failed: ${status.fail})` : ''}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setExpanded(!expanded)
            if (!expanded && networks.length === 0) startScan()
          }}
        >
          {expanded ? 'Close' : 'Change Wi-Fi'}
        </Button>
      </div>

      {expanded && (
        <div className="space-y-3 pt-1">
          <div className="flex items-center justify-between">
            <Label>Networks in range</Label>
            <Button
              variant="ghost"
              size="sm"
              className="gap-1.5 text-muted-foreground"
              disabled={scanning}
              onClick={startScan}
            >
              <span className={`material-icons-outlined text-base ${scanning ? 'animate-spin' : ''}`}>
                {scanning ? 'sync' : 'refresh'}
              </span>
              {scanning ? 'Scanning…' : 'Rescan'}
            </Button>
          </div>
          <div className="max-h-48 overflow-y-auto space-y-1">
            {networks.map((n) => (
              <button
                key={n.ssid}
                type="button"
                onClick={() => setSelectedSsid(n.ssid)}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-md border text-sm text-left transition-colors ${
                  selectedSsid === n.ssid ? 'border-primary bg-primary/5' : 'hover:bg-muted/50'
                }`}
              >
                <span className="truncate">{n.ssid}</span>
                <span className="flex items-center gap-1 text-muted-foreground shrink-0">
                  {(n.secure === 1 || n.secure === true) && (
                    <span className="material-icons-outlined text-sm">lock</span>
                  )}
                  <span className="material-icons-outlined text-sm">
                    {n.rssi > -60 ? 'wifi' : n.rssi > -75 ? 'wifi_2_bar' : 'wifi_1_bar'}
                  </span>
                </span>
              </button>
            ))}
            {!scanning && networks.length === 0 && (
              <p className="text-xs text-muted-foreground py-2">No networks found - rescan.</p>
            )}
          </div>
          {selectedSsid && (
            <div className="flex gap-3">
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={`Password for "${selectedSsid}" (8-64 chars)`}
                autoCapitalize="none"
                autoCorrect="off"
                className="flex-1"
              />
              <Button
                disabled={busy === 'join' || password.length < 8}
                onClick={joinNetwork}
              >
                {busy === 'join' ? (
                  <span className="material-icons-outlined animate-spin">sync</span>
                ) : (
                  'Connect'
                )}
              </Button>
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            The table reboots to join the new network. If it lands on a different
            address, this server re-finds it automatically via mDNS.
          </p>
          <div className="pt-1">
            <Button
              variant="outline"
              size="sm"
              className="text-destructive border-destructive/40 hover:bg-destructive/10"
              disabled={busy === 'standalone' || status.mode === 'standalone'}
              onClick={switchToStandalone}
            >
              Switch to standalone hotspot
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
