import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { apiClient } from '@/lib/apiClient'
import { useStatusStore } from '@/stores/useStatusStore'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'

const DEG = Math.PI / 180

/**
 * Crash-homing orientation alignment (parity with dune-weaver-mobile's
 * AlignOrientation). Crash homing never moves theta — whatever direction the
 * arm points when the table homes BECOMES theta=0, so pattern orientation is
 * set physically: walk the ball to the table's "East" (directly to your right
 * when facing the table), then home to lock it in.
 *
 * Nudges are absolute jogs seeded from the live status theta. Taps accumulate
 * into a target angle; one pump loop pushes the latest value, retrying while
 * the firmware answers 409 (previous jog still finishing).
 */
export function AlignOrientationDialog() {
  const [open, setOpen] = useState(false)
  const [homing, setHoming] = useState(false)
  const isRunning = useStatusStore((s) => s.status?.is_running ?? false)
  const isPaused = useStatusStore((s) => s.status?.is_paused ?? false)
  const isHoming = useStatusStore((s) => s.status?.is_homing ?? false)
  const isAlarm = useStatusStore((s) => s.status?.is_alarm ?? false)

  const canNudge = !isAlarm && !isRunning && !isPaused && !isHoming
  const canHome = !isRunning && !isPaused && !isHoming

  const targetRef = useRef<number | null>(null)
  const pumping = useRef(false)

  const nudge = (deg: number) => {
    const liveTheta = useStatusStore.getState().status?.current_theta ?? 0
    const cur = targetRef.current ?? liveTheta
    targetRef.current = cur + deg * DEG
    void pump()
  }

  const pump = async () => {
    if (pumping.current) return
    pumping.current = true
    try {
      let sent: number | null = null
      let waitedMs = 0
      while (targetRef.current != null && targetRef.current !== sent) {
        sent = targetRef.current
        try {
          await apiClient.post('/api/board/rotate', { theta: sent })
          waitedMs = 0
        } catch (e) {
          const msg = e instanceof Error ? e.message : ''
          if (!msg.startsWith('HTTP 409') || waitedMs > 15000) throw e
          await new Promise((r) => setTimeout(r, 400))
          waitedMs += 400
          sent = null // resend the (possibly updated) target
        }
      }
    } catch {
      toast.error('Could not rotate the arm')
      targetRef.current = null
    } finally {
      pumping.current = false
    }
  }

  const toEdge = async () => {
    try {
      await apiClient.post('/move_to_perimeter')
      toast.success('Moving to the edge')
    } catch {
      toast.error('Could not move the ball')
    }
  }

  // Homing re-declares the current arm angle as theta=0 (crash mode), so the
  // accumulated nudge frame is stale afterwards — drop it.
  const setOrientation = async () => {
    setHoming(true)
    try {
      await apiClient.post('/send_home')
      targetRef.current = null
      setOpen(false)
      toast.success('Orientation set - homing now')
    } catch {
      toast.error('Could not home the table')
    } finally {
      setHoming(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) targetRef.current = null
        setOpen(o)
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" className="gap-2">
          <span className="material-icons-outlined text-base">screen_rotation</span>
          Align Pattern Orientation
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Align orientation</DialogTitle>
          <DialogDescription>
            With crash homing, patterns are oriented by where the arm points when the
            table homes. Align it once so patterns come out matching their previews.
          </DialogDescription>
        </DialogHeader>

        {/* Table seen from above, viewer at the bottom. Target = 3 o'clock,
            i.e. theta=0 in the preview frame ("arm points East"). */}
        <div className="flex justify-center py-2">
          <div className="relative w-[190px] h-[190px]">
            <svg width={190} height={190}>
              <circle cx={95} cy={95} r={83} className="stroke-border fill-muted/40" strokeWidth={2} />
              <circle cx={95 + 83 - 9} cy={95} r={9} className="fill-primary" />
            </svg>
            <div className="absolute left-1/2 -translate-x-1/2 bottom-[-6px] flex items-center gap-1 px-2 py-0.5 rounded-full border bg-background text-muted-foreground text-xs">
              <span className="material-icons-outlined text-sm">person</span>
              You
            </div>
          </div>
        </div>

        <ol className="text-xs text-muted-foreground list-decimal pl-4 space-y-1">
          <li>Stand where you normally look at the table from.</li>
          <li>
            Use the arrows to walk the ball around the edge until it sits directly to
            your <span className="font-medium text-foreground">right</span> (the
            highlighted spot).
          </li>
          <li>Press "Set orientation" - the table homes and locks that in.</li>
        </ol>

        <div className="flex justify-center gap-2">
          {(
            [
              ['rotate_left', -45, '45°'],
              ['rotate_left', -10, '10°'],
              ['rotate_right', 10, '10°'],
              ['rotate_right', 45, '45°'],
            ] as const
          ).map(([icon, deg, label]) => (
            <Button
              key={deg}
              variant="outline"
              size="sm"
              disabled={!canNudge}
              onClick={() => nudge(deg)}
              className="gap-1"
            >
              <span className="material-icons-outlined text-base">{icon}</span>
              {label}
            </Button>
          ))}
        </div>

        <div className="flex flex-col gap-2">
          <Button variant="secondary" disabled={!canNudge} onClick={toEdge} className="gap-2">
            <span className="material-icons-outlined text-base">trip_origin</span>
            Move ball to the edge
          </Button>
          <Button disabled={!canHome || homing} onClick={setOrientation} className="gap-2">
            {homing ? (
              <span className="material-icons-outlined text-base animate-spin">sync</span>
            ) : (
              <span className="material-icons-outlined text-base">check</span>
            )}
            Set orientation (homes the table)
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
