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
  url: string
  host?: string
  port?: number
  version?: string
  isOnline?: boolean
  isCurrent?: boolean // True if this is the backend serving the frontend
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
            setActiveTableState(active)
            apiClient.setBaseUrl(active.url === `http://localhost:${window.location.port || 8080}` ? '' : active.url)
          }
        }
      }

      // Auto-discover on first load if no tables saved
      if (!stored) {
        discoverTables()
      }
    } catch (e) {
      console.error('Failed to load saved tables:', e)
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

  // Set active table and update API client
  const setActiveTable = useCallback((table: Table) => {
    setActiveTableState(table)

    // Update API client base URL
    // If the table is the current one (serving this frontend), use relative URLs
    if (table.isCurrent || table.url === window.location.origin) {
      apiClient.setBaseUrl('')
    } else {
      apiClient.setBaseUrl(table.url)
    }
  }, [])

  // Discover tables via mDNS
  const discoverTables = useCallback(async () => {
    setIsDiscovering(true)

    try {
      // Call the discovery endpoint on the current backend
      const response = await fetch('/api/discover-tables?timeout=3')
      if (!response.ok) {
        throw new Error('Discovery failed')
      }

      const data = await response.json()
      const discoveredTables: Table[] = (data.tables || []).map((t: {
        id: string
        name: string
        url: string
        host?: string
        port?: number
        version?: string
        is_current?: boolean
      }) => ({
        id: t.id,
        name: t.name,
        url: t.url,
        host: t.host,
        port: t.port,
        version: t.version,
        isOnline: true,
        isCurrent: t.is_current || false,
      }))

      // Merge with existing tables (keep manual additions)
      setTables(prev => {
        const merged = [...discoveredTables]

        // Add any manually added tables that weren't discovered
        prev.forEach(existing => {
          if (!merged.find(t => t.id === existing.id)) {
            merged.push({ ...existing, isOnline: false })
          }
        })

        return merged
      })

      // If no active table, select the current one
      if (!activeTable) {
        const currentTable = discoveredTables.find(t => t.isCurrent)
        if (currentTable) {
          setActiveTable(currentTable)
        }
      }

      setLastDiscovery(new Date())
    } catch (e) {
      console.error('Table discovery failed:', e)

      // If discovery fails and we have no tables, add the current backend
      if (tables.length === 0) {
        try {
          const infoResponse = await fetch('/api/table-info')
          if (infoResponse.ok) {
            const info = await infoResponse.json()
            const currentTable: Table = {
              id: info.id,
              name: info.name,
              url: window.location.origin,
              version: info.version,
              isOnline: true,
              isCurrent: true,
            }
            setTables([currentTable])
            setActiveTable(currentTable)
          }
        } catch {
          // Ignore
        }
      }
    } finally {
      setIsDiscovering(false)
    }
  }, [activeTable, tables.length, setActiveTable])

  // Add a table manually by URL
  const addTable = useCallback(async (url: string, name?: string): Promise<Table | null> => {
    try {
      // Normalize URL
      const normalizedUrl = url.replace(/\/$/, '')

      // Check if already exists
      if (tables.find(t => t.url === normalizedUrl)) {
        return null
      }

      // Fetch table info from the URL
      const response = await fetch(`${normalizedUrl}/api/table-info`)
      if (!response.ok) {
        throw new Error('Failed to fetch table info')
      }

      const info = await response.json()
      const newTable: Table = {
        id: info.id,
        name: name || info.name,
        url: normalizedUrl,
        version: info.version,
        isOnline: true,
        isCurrent: false,
      }

      setTables(prev => [...prev, newTable])
      return newTable
    } catch (e) {
      console.error('Failed to add table:', e)
      return null
    }
  }, [tables])

  // Remove a table
  const removeTable = useCallback((id: string) => {
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

  // Check if a table is online
  const refreshTableStatus = useCallback(async (table: Table): Promise<boolean> => {
    try {
      const baseUrl = table.isCurrent ? '' : table.url
      const response = await fetch(`${baseUrl}/api/table-info`, {
        signal: AbortSignal.timeout(3000),
      })
      const isOnline = response.ok

      setTables(prev =>
        prev.map(t => (t.id === table.id ? { ...t, isOnline } : t))
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
