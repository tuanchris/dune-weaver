/**
 * TableSelector - Header component for switching between sand tables
 *
 * Displays the current table and provides a dropdown to switch between
 * discovered tables or add new ones manually.
 */

import { useState } from 'react'
import { useTable, type Table } from '@/contexts/TableContext'
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
  Wifi,
  WifiOff,
  Pencil,
  Trash2,
  ChevronDown,
} from 'lucide-react'

export function TableSelector() {
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
        toast.error('Failed to add table. Check the URL and try again.')
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
          <Button
            variant="ghost"
            size="sm"
            className="gap-2 h-9 px-3"
          >
            <Layers className="h-4 w-4" />
            <span className="hidden sm:inline max-w-[120px] truncate">
              {activeTable?.appName || activeTable?.name || 'Select Table'}
            </span>
            <ChevronDown className="h-3 w-3 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-72 p-2" align="end">
          <div className="space-y-2">
            {/* Header */}
            <div className="px-2 py-1">
              <span className="text-sm font-medium">Sand Tables</span>
            </div>

            {/* Table list */}
            <div className="space-y-1">
              {tables.map(table => (
                <div
                  key={table.id}
                  className={`flex items-center gap-2 px-2 py-2 rounded-md cursor-pointer hover:bg-accent group ${
                    activeTable?.id === table.id ? 'bg-accent' : ''
                  }`}
                  onClick={() => handleSelectTable(table)}
                >
                  {/* Status indicator */}
                  {table.isOnline ? (
                    <Wifi className="h-3.5 w-3.5 text-green-500 flex-shrink-0" />
                  ) : (
                    <WifiOff className="h-3.5 w-3.5 text-red-500 flex-shrink-0" />
                  )}

                  {/* Name and info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm truncate">{table.name}</span>
                      {table.isCurrent && (
                        <Badge variant="secondary" className="text-[10px] px-1 py-0">
                          This
                        </Badge>
                      )}
                    </div>
                    <span className="text-xs text-muted-foreground truncate block">
                      {table.host || new URL(table.url).hostname}
                    </span>
                  </div>

                  {/* Selected indicator */}
                  {activeTable?.id === table.id && (
                    <Check className="h-4 w-4 text-primary flex-shrink-0" />
                  )}

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
                </div>
              ))}
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
          <DialogFooter>
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
          <DialogFooter>
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
