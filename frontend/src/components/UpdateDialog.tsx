import { useState, useEffect, useRef } from 'react'
import { apiClient } from '@/lib/apiClient'
import { useStatusStore } from '@/stores/useStatusStore'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface UpdateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  currentVersion: string
  latestVersion: string
}

type UpdateState = 'confirming' | 'updating' | 'complete' | 'error'

const FUN_MESSAGES = [
  'Shifting the sands...',
  'Aligning the stars...',
  'Polishing the steel ball...',
  'Recalculating the spirals...',
  'Tuning the motors...',
  'Almost there...',
]

export function UpdateDialog({ open, onOpenChange, currentVersion, latestVersion }: UpdateDialogProps) {
  const [state, setState] = useState<UpdateState>('confirming')
  const [errorMessage, setErrorMessage] = useState('')
  const [messageIndex, setMessageIndex] = useState(0)
  const messageRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // Track that we've seen the WS go down (so reconnect means update finished)
  const sawDisconnect = useRef(false)

  const isBackendConnected = useStatusStore((s) => s.isBackendConnected)

  // Reset state when dialog closes
  useEffect(() => {
    if (!open) {
      if (messageRef.current) clearInterval(messageRef.current)
      setState('confirming')
      setErrorMessage('')
      setMessageIndex(0)
      sawDisconnect.current = false
    }
  }, [open])

  // Track WS disconnect/reconnect while updating
  useEffect(() => {
    if (state !== 'updating') return

    if (!isBackendConnected) {
      sawDisconnect.current = true
    } else if (sawDisconnect.current) {
      // WS came back after being down — update is done
      setState('complete')
    }
  }, [state, isBackendConnected])

  // Auto-reload shortly after complete
  useEffect(() => {
    if (state !== 'complete') return
    const timer = setTimeout(() => window.location.reload(), 2000)
    return () => clearTimeout(timer)
  }, [state])

  // Rotate fun messages every 4 seconds while updating
  useEffect(() => {
    if (state !== 'updating') return
    messageRef.current = setInterval(() => {
      setMessageIndex(i => (i + 1) % FUN_MESSAGES.length)
    }, 4000)
    return () => {
      if (messageRef.current) clearInterval(messageRef.current)
    }
  }, [state])

  const handleUpdate = async () => {
    setState('updating')
    setMessageIndex(0)
    sawDisconnect.current = false
    try {
      const res = await apiClient.request<{ success: boolean; message: string }>('/api/update', {
        method: 'POST',
      })
      if (!res.success) {
        setState('error')
        setErrorMessage(res.message || 'Update failed')
      }
    } catch (err) {
      setState('error')
      setErrorMessage(err instanceof Error ? err.message : 'Failed to start update')
    }
  }

  const isBlocked = state === 'updating' || state === 'complete'

  return (
    <Dialog open={open} onOpenChange={isBlocked ? undefined : onOpenChange}>
      <DialogContent
        onPointerDownOutside={isBlocked ? (e) => e.preventDefault() : undefined}
        onEscapeKeyDown={isBlocked ? (e) => e.preventDefault() : undefined}
        className={isBlocked ? '[&>button:last-child]:hidden' : ''}
      >
        {state === 'confirming' && (
          <>
            <DialogHeader>
              <DialogTitle>Update Software</DialogTitle>
              <DialogDescription>
                Update from v{currentVersion} to v{latestVersion}
              </DialogDescription>
            </DialogHeader>
            <p className="text-sm text-muted-foreground">
              The system will download the latest version and restart automatically.
              This usually takes 1-2 minutes.
            </p>
            <DialogFooter>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button onClick={handleUpdate}>
                Update Now
              </Button>
            </DialogFooter>
          </>
        )}

        {state === 'updating' && (
          <div className="flex flex-col items-center py-8 gap-6">
            <div className="relative w-16 h-16">
              <div className="absolute inset-0 rounded-full border-4 border-muted" />
              <div className="absolute inset-0 rounded-full border-4 border-t-primary animate-spin" />
              <div className="absolute inset-[6px] rounded-full border-4 border-muted" />
              <div
                className="absolute inset-[6px] rounded-full border-4 border-t-primary/60"
                style={{ animation: 'spin 1.5s linear infinite reverse' }}
              />
            </div>
            <div className="text-center space-y-2">
              <p className="text-lg font-medium animate-pulse">
                {FUN_MESSAGES[messageIndex]}
              </p>
              <p className="text-sm text-muted-foreground">
                This usually takes 1-2 minutes.
                <br />
                The page will reload automatically.
              </p>
            </div>
          </div>
        )}

        {state === 'complete' && (
          <div className="flex flex-col items-center py-8 gap-4">
            <div className="w-16 h-16 flex items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
              <span className="material-icons text-green-600 dark:text-green-400 text-4xl">check_circle</span>
            </div>
            <div className="text-center space-y-1">
              <p className="text-lg font-medium">Update complete!</p>
              <p className="text-sm text-muted-foreground">Reloading...</p>
            </div>
          </div>
        )}

        {state === 'error' && (
          <>
            <DialogHeader>
              <DialogTitle>Update Failed</DialogTitle>
              <DialogDescription>
                Something went wrong while starting the update.
              </DialogDescription>
            </DialogHeader>
            <div className="rounded-lg bg-destructive/10 p-3">
              <p className="text-sm text-destructive">{errorMessage}</p>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Close
              </Button>
              <Button onClick={handleUpdate}>
                Retry
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
