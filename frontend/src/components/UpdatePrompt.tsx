import { useRegisterSW } from 'virtual:pwa-register/react'
import { Button } from '@/components/ui/button'

/**
 * Shows a toast-like card when a new service worker is waiting,
 * letting the user choose when to apply the update instead of
 * hot-swapping the SW mid-session (registerType: 'prompt').
 */
export function UpdatePrompt() {
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW()

  if (!needRefresh) return null

  return (
    <div
      role="alert"
      className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 rounded-lg border bg-card text-card-foreground shadow-lg px-4 py-3"
    >
      <span className="text-sm font-medium">Update available</span>
      <Button size="sm" onClick={() => updateServiceWorker(true)}>
        Reload
      </Button>
      <Button size="sm" variant="ghost" onClick={() => setNeedRefresh(false)}>
        Dismiss
      </Button>
    </div>
  )
}
