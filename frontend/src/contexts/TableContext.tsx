/**
 * TableContext - Multi-table state management
 *
 * Manages discovered tables, active table selection, and persistence.
 * When the active table changes, the API client's base URL is updated
 * and components can react to reconnect WebSockets.
 */

import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import { apiClient } from '@/lib/apiClient'

export interface Table {
  id: string
  name: string
  appName?: string // Application name from settings (e.g., "Dune Weaver")
  url: string
  host?: string
  port?: number
  version?: string
  isOnline?: boolean
  isCurrent?: boolean // True if this is the backend serving the frontend
  customLogo?: string // Custom logo filename if set (e.g., "logo_abc123.png")
}

interface TableContextType {
  // State
  tables: Table[]
  activeTable: Table | null
  isDiscovering: boolean
  lastDiscovery: Date | null

  // Actions
  setActiveTable: (table: Table) => void
  discoverTables: () => Promise<void>
  addTable: (url: string, name?: string) => Promise<Table | null>
  removeTable: (id: string) => void
  updateTableName: (id: string, name: string) => Promise<void>
  refreshTableStatus: (table: Table) => Promise<boolean>
}

const TableContext = createContext<TableContextType | null>(null)

const STORAGE_KEY = 'duneweaver_tables'
const ACTIVE_TABLE_KEY = 'duneweaver_active_table'

/**
 * Normalize a URL to its origin for comparison purposes.
 * This handles port normalization (e.g., :80 for HTTP is stripped).
 * Returns the origin or the original string if parsing fails.
 */
function normalizeUrlOrigin(url: string): string {
  try {
    return new URL(url).origin
  } catch {
    return url
  }
}

interface StoredTableData {
  tables: Table[]
  activeTableId: string | null
}

export function TableProvider({ children }: { children: React.ReactNode }) {
  const [tables, setTables] = useState<Table[]>([])
  const [activeTable, setActiveTableState] = useState<Table | null>(null)
  const [isDiscovering, setIsDiscovering] = useState(false)
  const [lastDiscovery, setLastDiscovery] = useState<Date | null>(null)
  const initializedRef = useRef(false)
  const restoredActiveIdRef = useRef<string | null>(null) // Track restored selection

  // Load saved tables from localStorage on mount
  useEffect(() => {
    if (initializedRef.current) return
    initializedRef.current = true

    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      const activeId = localStorage.getItem(ACTIVE_TABLE_KEY)

      if (stored) {
        const data: StoredTableData = JSON.parse(stored)
        setTables(data.tables || [])

        // Restore active table
        if (activeId && data.tables) {
          const active = data.tables.find(t => t.id === activeId)
          if (active) {
            restoredActiveIdRef.current = activeId // Mark that we restored a selection
            setActiveTableState(active)
            // Set base URL for remote tables (tables not on the current origin)
            // Use normalized URL comparison to handle port differences (e.g., :80 vs no port)
            // Don't rely on isCurrent flag as it may be stale from localStorage
            const normalizedActiveUrl = normalizeUrlOrigin(active.url)
            const currentOrigin = window.location.origin
            const isRemoteTable = normalizedActiveUrl !== currentOrigin
            console.log('[TableContext] Restoring active table:', {
              activeId,
              activeUrl: active.url,
              normalizedActiveUrl,
              currentOrigin,
              isRemoteTable,
              willSetBaseUrl: isRemoteTable,
            })
            if (isRemoteTable) {
              apiClient.setBaseUrl(active.url)
            }
          }
        }
      }

      // Always refresh to ensure current table is available and up-to-date
      discoverTables()
    } catch (e) {
      console.error('Failed to load saved tables:', e)
      discoverTables()
    }
  }, [])

  // Save tables to localStorage when they change
  useEffect(() => {
    if (!initializedRef.current) return

    try {
      const data: StoredTableData = {
        tables,
        activeTableId: activeTable?.id || null,
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
      if (activeTable) {
        localStorage.setItem(ACTIVE_TABLE_KEY, activeTable.id)
      } else {
        localStorage.removeItem(ACTIVE_TABLE_KEY)
      }
    } catch (e) {
      console.error('Failed to save tables:', e)
    }
  }, [tables, activeTable])

  // Set active table - saves to localStorage and reloads page for clean state
  const setActiveTable = useCallback((table: Table) => {
    // Save to localStorage before reload
    try {
      const currentTables = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
      const data: StoredTableData = {
        tables: currentTables.tables || tables,
        activeTableId: table.id,
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
      localStorage.setItem(ACTIVE_TABLE_KEY, table.id)
    } catch (e) {
      console.error('Failed to save table selection:', e)
    }

    // Update API client base URL
    // Use normalized URL comparison to handle port differences (e.g., :80 vs no port)
    if (normalizeUrlOrigin(table.url) === window.location.origin) {
      apiClient.setBaseUrl('')
    } else {
      apiClient.setBaseUrl(table.url)
    }

    // Reload page for clean state (WebSockets, caches, etc.)
    window.location.reload()
  }, [tables])

  // Refresh tables - ensures current table is always available
  const discoverTables = useCallback(async () => {
    setIsDiscovering(true)

    try {
      // Fetch table info, settings, and known tables in parallel
      const [infoResponse, settingsResponse, knownTablesResponse] = await Promise.all([
        fetch('/api/table-info'),
        fetch('/api/settings').catch(() => null),
        fetch('/api/known-tables').catch(() => null),
      ])

      if (!infoResponse.ok) {
        throw new Error('Failed to fetch table info')
      }

      const info = await infoResponse.json()
      const settings = settingsResponse?.ok ? await settingsResponse.json() : null
      const knownTablesData = knownTablesResponse?.ok ? await knownTablesResponse.json() : null
      const knownTables: Array<{ id: string; name: string; url: string; host?: string; port?: number; version?: string }> = knownTablesData?.tables || []

      const currentTable: Table = {
        id: info.id,
        name: info.name,
        url: window.location.origin,
        version: info.version,
        isOnline: true,
        isCurrent: true,
        customLogo: settings?.app?.custom_logo || undefined,
      }

      // Merge current table with known tables from backend
      setTables(() => {
        // Start with current table
        const merged: Table[] = [currentTable]

        // Add known tables from backend (these are persisted remote tables)
        knownTables.forEach(known => {
          if (known.id !== currentTable.id) {
            merged.push({
              id: known.id,
              name: known.name,
              url: known.url,
              host: known.host,
              port: known.port,
              version: known.version,
              isOnline: false, // Will be updated by background refresh
              isCurrent: false,
            })
          }
        })

        return merged
      })

      // If no active table AND no restored selection, select the current one
      // Use ref to check restored selection because activeTable state may not be updated yet
      if (!activeTable && !restoredActiveIdRef.current) {
        // For initial selection of current table, just update state without reload
        // Reload is only needed when switching between DIFFERENT tables
        setActiveTableState(currentTable)
        // Save to localStorage so it persists
        try {
          const data: StoredTableData = {
            tables: [currentTable],
            activeTableId: currentTable.id,
          }
          localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
          localStorage.setItem(ACTIVE_TABLE_KEY, currentTable.id)
        } catch (e) {
          console.error('Failed to save initial table selection:', e)
        }
      } else if (activeTable?.isCurrent) {
        // Update active table name if it changed on the backend
        setActiveTableState(prev => prev ? { ...prev, name: currentTable.name } : null)
      }
      // Clear the restored ref after first discovery
      restoredActiveIdRef.current = null

      setLastDiscovery(new Date())

      // Refresh remote tables in the background to get their customLogo
      // Use setTimeout to not block the main discovery flow
      setTimeout(() => {
        setTables(currentTables => {
          const remoteTables = currentTables.filter(t => !t.isCurrent)
          remoteTables.forEach(async (table) => {
            try {
              const [infoResponse, settingsResponse] = await Promise.all([
                fetch(`${table.url}/api/table-info`, { signal: AbortSignal.timeout(3000) }),
                fetch(`${table.url}/api/settings`, { signal: AbortSignal.timeout(3000) }).catch(() => null),
              ])
              const isOnline = infoResponse.ok
              const settings = settingsResponse?.ok ? await settingsResponse.json() : null
              const customLogo = settings?.app?.custom_logo || undefined

              setTables(prev =>
                prev.map(t => (t.id === table.id ? { ...t, isOnline, customLogo } : t))
              )
            } catch {
              setTables(prev =>
                prev.map(t => (t.id === table.id ? { ...t, isOnline: false } : t))
              )
            }
          })
          return currentTables // Return unchanged for now, updates happen in the async callbacks
        })
      }, 100)
    } catch (e) {
      console.error('Table refresh failed:', e)
    } finally {
      setIsDiscovering(false)
    }
  }, [activeTable]) // Only depends on activeTable for checking if we need to update name

  // Add a table manually by URL
  const addTable = useCallback(async (url: string, name?: string): Promise<Table | null> => {
    try {
      // Normalize URL
      const normalizedUrl = url.replace(/\/$/, '')

      // Check if already exists
      if (tables.find(t => t.url === normalizedUrl)) {
        return null
      }

      // Fetch table info and settings in parallel
      const [infoResponse, settingsResponse] = await Promise.all([
        fetch(`${normalizedUrl}/api/table-info`),
        fetch(`${normalizedUrl}/api/settings`).catch(() => null),
      ])

      if (!infoResponse.ok) {
        throw new Error('Failed to fetch table info')
      }

      const info = await infoResponse.json()
      const settings = settingsResponse?.ok ? await settingsResponse.json() : null

      const newTable: Table = {
        id: info.id,
        name: name || info.name,
        url: normalizedUrl,
        version: info.version,
        isOnline: true,
        isCurrent: false,
        customLogo: settings?.app?.custom_logo || undefined,
      }

      // Persist to backend
      try {
        const hostname = new URL(normalizedUrl).hostname
        await fetch('/api/known-tables', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            id: newTable.id,
            name: newTable.name,
            url: newTable.url,
            host: hostname,
            version: newTable.version,
          }),
        })
      } catch (e) {
        console.error('Failed to persist table to backend:', e)
        // Continue anyway - table will still work for this session
      }

      setTables(prev => [...prev, newTable])
      return newTable
    } catch (e) {
      console.error('Failed to add table:', e)
      return null
    }
  }, [tables])

  // Remove a table
  const removeTable = useCallback(async (id: string) => {
    // Remove from backend
    try {
      await fetch(`/api/known-tables/${id}`, { method: 'DELETE' })
    } catch (e) {
      console.error('Failed to remove table from backend:', e)
      // Continue anyway - remove from local state
    }

    setTables(prev => prev.filter(t => t.id !== id))

    // If removing active table, switch to another
    if (activeTable?.id === id) {
      const remaining = tables.filter(t => t.id !== id)
      if (remaining.length > 0) {
        setActiveTable(remaining[0])
      } else {
        setActiveTableState(null)
        apiClient.setBaseUrl('')
      }
    }
  }, [activeTable, tables, setActiveTable])

  // Update table name (on the backend)
  const updateTableName = useCallback(async (id: string, name: string) => {
    const table = tables.find(t => t.id === id)
    if (!table) return

    try {
      const baseUrl = table.isCurrent ? '' : table.url
      const response = await fetch(`${baseUrl}/api/table-info`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })

      if (response.ok) {
        // Also update the known table name in the current backend (for remote tables)
        if (!table.isCurrent) {
          try {
            await fetch(`/api/known-tables/${id}`, {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ name }),
            })
          } catch (e) {
            console.error('Failed to update known table name:', e)
          }
        }

        setTables(prev =>
          prev.map(t => (t.id === id ? { ...t, name } : t))
        )

        // Update active table if it's the one being renamed
        if (activeTable?.id === id) {
          setActiveTableState(prev => prev ? { ...prev, name } : null)
        }
      }
    } catch (e) {
      console.error('Failed to update table name:', e)
    }
  }, [tables, activeTable])

  // Check if a table is online and update its info (including custom logo)
  const refreshTableStatus = useCallback(async (table: Table): Promise<boolean> => {
    try {
      const baseUrl = table.isCurrent ? '' : table.url

      // Fetch table info and settings in parallel
      const [infoResponse, settingsResponse] = await Promise.all([
        fetch(`${baseUrl}/api/table-info`, { signal: AbortSignal.timeout(3000) }),
        fetch(`${baseUrl}/api/settings`, { signal: AbortSignal.timeout(3000) }).catch(() => null),
      ])

      const isOnline = infoResponse.ok
      const settings = settingsResponse?.ok ? await settingsResponse.json() : null
      const customLogo = settings?.app?.custom_logo || undefined

      setTables(prev =>
        prev.map(t => (t.id === table.id ? { ...t, isOnline, customLogo } : t))
      )

      return isOnline
    } catch {
      setTables(prev =>
        prev.map(t => (t.id === table.id ? { ...t, isOnline: false } : t))
      )
      return false
    }
  }, [])

  return (
    <TableContext.Provider
      value={{
        tables,
        activeTable,
        isDiscovering,
        lastDiscovery,
        setActiveTable,
        discoverTables,
        addTable,
        removeTable,
        updateTableName,
        refreshTableStatus,
      }}
    >
      {children}
    </TableContext.Provider>
  )
}

export function useTable() {
  const context = useContext(TableContext)
  if (!context) {
    throw new Error('useTable must be used within a TableProvider')
  }
  return context
}

// Hook for subscribing to active table changes (for WebSocket reconnection)
export function useActiveTableChange(callback: (table: Table | null) => void) {
  const { activeTable } = useTable()
  const callbackRef = useRef(callback)
  const prevTableRef = useRef<Table | null>(null)

  callbackRef.current = callback

  useEffect(() => {
    // Only call on actual changes, not initial render
    if (prevTableRef.current !== null || activeTable !== null) {
      if (prevTableRef.current?.id !== activeTable?.id) {
        callbackRef.current(activeTable)
      }
    }
    prevTableRef.current = activeTable
  }, [activeTable])
}
