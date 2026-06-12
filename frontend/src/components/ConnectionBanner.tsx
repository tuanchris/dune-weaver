import { Link } from 'react-router-dom'
import { useStatusStore } from '@/stores/useStatusStore'

/**
 * Whether the sand table hardware (serial/WebSocket controller) is connected.
 * Distinct from isBackendConnected, which tracks the web backend itself.
 */
export function useTableConnected(): boolean {
  return useStatusStore((s) => Boolean(s.status?.connection_status))
}

/**
 * Inline banner shown when the table hardware is disconnected, with a path
 * to recovery. Render near the top of pages whose primary actions need the
 * table (Browse, Playlists, Table Control, LED).
 */
export function ConnectionBanner() {
  const connected = useTableConnected()
  if (connected) return null

  return (
    <div
      role="status"
      className="flex items-center gap-2.5 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2.5 text-sm text-amber-700 dark:text-amber-400"
    >
      <span className="material-icons-outlined text-base shrink-0" aria-hidden="true">
        usb_off
      </span>
      <span className="min-w-0">
        Table not connected — patterns can't play.{' '}
        <Link
          to="/settings?section=connection"
          className="font-medium underline underline-offset-2 hover:text-amber-800 dark:hover:text-amber-300"
        >
          Connect
        </Link>
      </span>
    </div>
  )
}
