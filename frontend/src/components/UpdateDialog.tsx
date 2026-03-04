import { useState, useEffect, useCallback, useRef } from 'react'
import { apiClient } from '@/lib/apiClient'
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

type UpdateState = 'confirming' | 'updating' | 'error'

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
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const messageRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const cleanup = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    if (messageRef.current) {
      clearInterval(messageRef.current)
      messageRef.current = null
    }
  }, [])

  // Reset state when dialog closes
  useEffect(() => {
    if (!open) {
      cleanup()
      setState('confirming')
      setErrorMessage('')
      setMessageIndex(0)
    }
  }, [open, cleanup])

  // Cleanup on unmount
  useEffect(() => cleanup, [cleanup])

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

  // Poll backend every 3 seconds while updating
  useEffect(() => {
    if (state !== 'updating') return

    // Wait a few seconds before starting to poll (give the service time to go down)
    const startDelay = setTimeout(() => {
      pollRef.current = setInterval(async () => {
        try {
          await apiClient.request('/api/version')
          // Backend is back — reload the page
          cleanup()
          window.location.reload()
        } catch {
          // Still down, keep polling
        }
      }, 3000)
    }, 5000)

    return () => {
      clearTimeout(startDelay)
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [state, cleanup])

  const handleUpdate = async () => {
    setState('updating')
    setMessageIndex(0)
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

  const isUpdating = state === 'updating'

  return (
    <Dialog open={open} onOpenChange={isUpdating ? undefined : onOpenChange}>
      <DialogContent
        onPointerDownOutside={isUpdating ? (e) => e.preventDefault() : undefined}
        onEscapeKeyDown={isUpdating ? (e) => e.preventDefault() : undefined}
        className={isUpdating ? '[&>button:last-child]:hidden' : ''}
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
            {/* Animated spinner */}
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
