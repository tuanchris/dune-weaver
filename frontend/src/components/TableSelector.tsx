/**
 * TableSelector - Header component for switching between sand tables
 *
 * Displays the current table and provides a dropdown to switch between
 * discovered tables or add new ones manually.
 */

import { useState, useEffect, useCallback } from 'react'
import { useTable, type Table } from '@/contexts/TableContext'
import { apiClient } from '@/lib/apiClient'
import { useStatusStore } from '@/stores/useStatusStore'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { toast } from 'sonner'
import {
  Layers,
  Plus,
  Check,
  Pencil,
  Trash2,
  RefreshCw,
  Loader2,
} from 'lucide-react'

interface TableSelectorProps {
  children?: React.ReactNode
}

/** A FluidNC controller board found on the LAN via mDNS (`/api/discovered-boards`). */
interface DiscoveredBoard {
  name: string
  hostname: string | null
  host: string
  port: number
  url: string
  mac: string | null
}

/** `/serial_status` — which board this backend is bound to (its "added" board). */
interface ConnStatus {
  connected: boolean
  port?: string
  hostname?: string
}

type BoardStatus = 'connected' | 'added-offline' | 'available'
type BoardRow = DiscoveredBoard & { status: BoardStatus }

const hostFromUrl = (url: string): string => {
  try {
    return new URL(url).hostname
  } catch {
    return url.replace(/^https?:\/\//, '').split(':')[0]
  }
}

/**
 * Merge the mDNS board list with the backend's currently-configured board so the
 * dropdown can show "all boards + whether added or not":
 *  - connected     → this backend is bound to it right now (the added board, online)
 *  - added-offline → configured board that mDNS can't currently see
 *  - available     → discovered on the LAN but not connected here
 */
function buildBoardRows(boards: DiscoveredBoard[], conn: ConnStatus | null): BoardRow[] {
  const configuredUrl = conn?.port || null
  const matchesConfigured = (b: DiscoveredBoard): boolean =>
    !!configuredUrl &&
    (configuredUrl.includes(b.host) ||
      (!!b.hostname && configuredUrl.toLowerCase().includes(b.hostname.toLowerCase())))

  const rows: BoardRow[] = boards.map((b) => ({
    ...b,
    status: matchesConfigured(b) && conn?.connected ? 'connected' : 'available',
  }))

  // The configured board isn't advertising on mDNS right now — still show it,
  // so a moved/offline table doesn't silently vanish from the list.
  if (configuredUrl && !boards.some(matchesConfigured)) {
    rows.unshift({
      name: conn?.hostname || hostFromUrl(configuredUrl),
      hostname: conn?.hostname || null,
      host: hostFromUrl(configuredUrl),
      port: 80,
      url: configuredUrl,
      mac: null,
      status: conn?.connected ? 'connected' : 'added-offline',
    })
  }

  // Stable, connection-independent order so the list doesn't reshuffle when you
  // switch which board is connected — only the highlight moves.
  return rows.sort(
    (a, b) =>
      a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }) ||
      a.host.localeCompare(b.host)
  )
}

export function TableSelector({ children }: TableSelectorProps) {
  const {
    tables,
    activeTable,
    setActiveTable,
    addTable,
    removeTable,
    updateTableName,
  } = useTable()

  const [isOpen, setIsOpen] = useState(false)
  const [showAddDialog, setShowAddDialog] = useState(false)
  const [showRenameDialog, setShowRenameDialog] = useState(false)
  const [newTableUrl, setNewTableUrl] = useState('')
  const [newTableName, setNewTableName] = useState('')
  const [renameTable, setRenameTable] = useState<Table | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [isAdding, setIsAdding] = useState(false)

  // Controller boards on the LAN. The backend browses mDNS continuously, so a
  // GET is a cheap cache read; /serial_status tells us which board *this*
  // backend is currently bound to (the "added" one).
  const [boards, setBoards] = useState<DiscoveredBoard[]>([])
  const [conn, setConn] = useState<ConnStatus | null>(null)
  const [boardsLoading, setBoardsLoading] = useState(false)
  const [connectingUrl, setConnectingUrl] = useState<string | null>(null)

  const fetchBoards = useCallback(async () => {
    setBoardsLoading(true)
    try {
      const [boardData, connData] = await Promise.all([
        apiClient.get<{ boards: DiscoveredBoard[] }>('/api/discovered-boards').catch(() => null),
        apiClient.get<ConnStatus>('/serial_status').catch(() => null),
      ])
      setBoards(boardData?.boards || [])
      setConn(connData)
    } finally {
      setBoardsLoading(false)
    }
  }, [])

  // Refresh the board list whenever the dropdown opens.
  useEffect(() => {
    if (isOpen) fetchBoards()
  }, [isOpen, fetchBoards])

  // Also refresh when the connected board changes from elsewhere (Settings
  // connect/disconnect, or the server-side reconnect/relocate watchdog). Without
  // this, the dropdown keeps whatever it read on its last open and can disagree
  // with the Settings panel about which board is connected.
  useEffect(() => {
    const handler = () => fetchBoards()
    window.addEventListener('board-connected', handler)
    return () => window.removeEventListener('board-connected', handler)
  }, [fetchBoards])

  // The live connection flag comes over the status WebSocket. When it flips
  // (e.g. the watchdog re-points board_url after a DHCP move, with no explicit
  // event), re-read /serial_status so "Connected" tracks the real board.
  const liveConnected = useStatusStore((s) => s.status?.connection_status ?? false)
  useEffect(() => {
    fetchBoards()
  }, [liveConnected, fetchBoards])

  const handleConnectBoard = async (board: BoardRow) => {
    setConnectingUrl(board.url)
    try {
      const data = await apiClient.post<{ success?: boolean }>('/connect', { port: board.url })
      if (data.success) {
        toast.success(`Connected to ${board.name}`)
        // Let the header refresh its name to the newly-connected board.
        window.dispatchEvent(new CustomEvent('board-connected'))
        await fetchBoards()
      } else {
        toast.error(`Couldn't connect to ${board.name}`)
      }
    } catch (error) {
      if (error instanceof Error && error.message.startsWith('HTTP 401')) {
        toast.error(`${board.name} is password-protected — connect it from Settings`)
      } else {
        toast.error(`Couldn't reach ${board.name}`)
      }
    } finally {
      setConnectingUrl(null)
    }
  }

  const handleSelectTable = (table: Table) => {
    if (table.id !== activeTable?.id) {
      setActiveTable(table)
      toast.success(`Switched to ${table.name}`)
    }
    setIsOpen(false)
  }

  const handleAddTable = async () => {
    if (!newTableUrl.trim()) {
      toast.error('Please enter a URL')
      return
    }

    setIsAdding(true)
    try {
      // Ensure URL has protocol
      let url = newTableUrl.trim()
      if (!url.startsWith('http://') && !url.startsWith('https://')) {
        url = `http://${url}`
      }

      const table = await addTable(url, newTableName.trim() || undefined)
      if (table) {
        toast.success(`Added ${table.name}`)
        setShowAddDialog(false)
        setNewTableUrl('')
        setNewTableName('')
      } else {
        toast.error(
          "Couldn't reach a Dune Weaver server at that address. Use the address of the table's server (Raspberry Pi), not the controller board — tables on your network appear here automatically."
        )
      }
    } finally {
      setIsAdding(false)
    }
  }

  const handleRename = async () => {
    if (!renameTable || !renameValue.trim()) return

    await updateTableName(renameTable.id, renameValue.trim())
    toast.success('Table renamed')
    setShowRenameDialog(false)
    setRenameTable(null)
    setRenameValue('')
  }

  const handleRemove = (table: Table) => {
    if (table.isCurrent) {
      toast.error("Can't remove the current table")
      return
    }
    removeTable(table.id)
    toast.success(`Removed ${table.name}`)
  }

  const openRenameDialog = (table: Table) => {
    setRenameTable(table)
    setRenameValue(table.name)
    setShowRenameDialog(true)
  }

  // Always show if there are tables or discovering
  // This allows users to manually add tables even with just one

  return (
    <>
      <Popover open={isOpen} onOpenChange={setIsOpen}>
        <PopoverTrigger asChild>
          {children || (
            <Button
              variant="ghost"
              size="sm"
              className="gap-2 h-9 px-2"
            >
              <Layers className="h-4 w-4" />
              <span className="hidden sm:inline max-w-[120px] truncate">
                {activeTable?.appName || activeTable?.name || 'Select Table'}
              </span>
            </Button>
          )}
        </PopoverTrigger>
        <PopoverContent className="w-72 p-2" align="start" sideOffset={12} alignOffset={-56}>
          <div className="space-y-2">
            {/* Header */}
            <div className="px-2 py-1">
              <span className="text-sm font-medium">Sand Tables</span>
            </div>

            {/* Table list — only *other* Dune Weaver backends. The current
                backend isn't shown as a selectable row (the header already
                names it, and the connected board below carries "current"). */}
            <div className="space-y-1">
              {tables.filter(t => !t.isCurrent).map(table => (
                <div
                  key={table.id}
                  className={`flex items-center gap-2 px-2 py-2 rounded-md cursor-pointer hover:bg-accent group ${
                    activeTable?.id === table.id ? 'bg-accent' : ''
                  }`}
                  onClick={() => handleSelectTable(table)}
                >
                  {/* Table icon with status indicator */}
                  <div className="relative flex-shrink-0">
                    <img
                      src={
                        table.customLogo
                          ? `${table.isCurrent ? '' : table.url}/static/custom/${table.customLogo}`
                          : `${table.isCurrent ? '' : table.url}/static/android-chrome-192x192.png`
                      }
                      alt={table.name}
                      className="w-8 h-8 rounded-full object-cover"
                      onError={(e) => {
                        // Fallback to default icon if image fails to load
                        (e.target as HTMLImageElement).src = '/static/android-chrome-192x192.png'
                      }}
                    />
                    {/* Online status dot */}
                    <span
                      className={`absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-popover ${
                        table.isOnline ? 'bg-success' : 'bg-destructive'
                      }`}
                    />
                  </div>

                  {/* Name and info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm truncate">{table.name}</span>
                      {table.isCurrent && (
                        <Badge variant="secondary" className="text-[10px] px-1 py-0">
                          This
                        </Badge>
                      )}
                      {table.isDiscovered && (
                        <Badge variant="outline" className="text-[10px] px-1 py-0">
                          Discovered
                        </Badge>
                      )}
                    </div>
                    <span className="text-xs text-muted-foreground truncate block">
                      {table.host || new URL(table.url).hostname}
                    </span>
                  </div>

                  {/* Actions - always visible on mobile, hover on desktop */}
                  <div className="flex md:opacity-0 md:group-hover:opacity-100 items-center gap-1 transition-opacity">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0"
                      onClick={e => {
                        e.stopPropagation()
                        openRenameDialog(table)
                      }}
                      title="Rename"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    {!table.isCurrent && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                        onClick={e => {
                          e.stopPropagation()
                          handleRemove(table)
                        }}
                        title="Remove"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>

                  {/* Selected indicator - far right */}
                  {activeTable?.id === table.id && (
                    <Check className="h-4 w-4 text-primary flex-shrink-0" />
                  )}
                </div>
              ))}
            </div>

            {/* Controller boards on the LAN (mDNS), with added/connected status */}
            <div className="pt-1">
              <div className="flex items-center justify-between px-2 py-1">
                <span className="text-xs font-medium text-muted-foreground">
                  Boards on your network
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0 text-muted-foreground"
                  onClick={fetchBoards}
                  disabled={boardsLoading}
                  title="Rescan"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${boardsLoading ? 'animate-spin' : ''}`} />
                </Button>
              </div>

              {(() => {
                const boardRows = buildBoardRows(boards, conn)
                if (boardRows.length === 0) {
                  return (
                    <p className="px-2 py-1.5 text-xs text-muted-foreground">
                      {boardsLoading ? 'Scanning…' : 'No boards found on the network yet.'}
                    </p>
                  )
                }
                return (
                  <div className="space-y-1">
                    {boardRows.map((board) => (
                      <div
                        key={board.mac || board.url}
                        className={`flex items-center gap-2 px-2 py-2 rounded-md ${
                          board.status === 'connected' ? 'bg-accent' : ''
                        }`}
                      >
                        <div className="relative flex-shrink-0">
                          <img
                            src="/static/android-chrome-192x192.png"
                            alt={board.name}
                            className="w-8 h-8 rounded-full object-cover"
                          />
                          {/* The dot is reachability ("can we ping it"): a board
                              on mDNS is reachable (green); a configured board
                              mDNS can't see is unreachable (red). Connection is
                              shown separately by the "Connected" label. */}
                          <span
                            className={`absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-popover ${
                              board.status === 'added-offline' ? 'bg-destructive' : 'bg-success'
                            }`}
                            title={board.status === 'added-offline' ? 'Unreachable' : 'Reachable'}
                          />
                        </div>

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm truncate">{board.name}</span>
                            {board.status === 'connected' && (
                              <Badge variant="secondary" className="text-[10px] px-1 py-0">
                                Added
                              </Badge>
                            )}
                            {board.status === 'added-offline' && (
                              <Badge variant="outline" className="text-[10px] px-1 py-0">
                                Added · offline
                              </Badge>
                            )}
                          </div>
                          <span className="text-xs text-muted-foreground truncate block">
                            {board.host}
                          </span>
                        </div>

                        {board.status === 'connected' ? (
                          <div className="flex items-center gap-1.5 shrink-0">
                            <span className="text-xs font-medium text-success">
                              Connected
                            </span>
                            <Check className="h-4 w-4 text-primary" />
                          </div>
                        ) : board.status === 'available' ? (
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 shrink-0"
                            disabled={connectingUrl === board.url}
                            onClick={() => handleConnectBoard(board)}
                          >
                            {connectingUrl === board.url ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              'Connect'
                            )}
                          </Button>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 shrink-0 text-muted-foreground"
                            disabled={connectingUrl === board.url}
                            onClick={() => handleConnectBoard(board)}
                            title="Retry connection"
                          >
                            {connectingUrl === board.url ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              'Reconnect'
                            )}
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                )
              })()}
            </div>

            {/* Add table button */}
            <Button
              variant="secondary"
              size="sm"
              className="w-full gap-2"
              onClick={() => setShowAddDialog(true)}
            >
              <Plus className="h-3.5 w-3.5" />
              Add Table Manually
            </Button>
          </div>
        </PopoverContent>
      </Popover>

      {/* Add Table Dialog */}
      <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Table Manually</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Table URL</label>
              <Input
                placeholder="192.168.1.100:8080 or http://..."
                value={newTableUrl}
                onChange={e => setNewTableUrl(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleAddTable()}
              />
              <p className="text-xs text-muted-foreground">
                Enter the IP address and port of the table's backend
              </p>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Name (optional)</label>
              <Input
                placeholder="Living Room Table"
                value={newTableName}
                onChange={e => setNewTableName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleAddTable()}
              />
            </div>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="secondary" onClick={() => setShowAddDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleAddTable} disabled={isAdding}>
              {isAdding ? 'Adding...' : 'Add Table'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Rename Dialog */}
      <Dialog open={showRenameDialog} onOpenChange={setShowRenameDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename Table</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <Input
              placeholder="Table name"
              value={renameValue}
              onChange={e => setRenameValue(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleRename()}
              autoFocus
            />
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="secondary" onClick={() => setShowRenameDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleRename}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
