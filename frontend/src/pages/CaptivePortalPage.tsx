import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export function CaptivePortalPage() {
  const navigate = useNavigate()
  const [showUrlHint, setShowUrlHint] = useState(false)

  const handleControlTable = () => {
    // Try to open in real browser (outside captive portal webview)
    const url = 'http://10.42.0.1'
    const w = window.open(url, '_blank')
    if (!w || w.closed) {
      // window.open blocked — show URL for user to open manually
      setShowUrlHint(true)
    }
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4">
      <div className="w-full max-w-sm text-center space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">Welcome to Dune Weaver</h1>
          <p className="text-muted-foreground mt-2">What would you like to do?</p>
        </div>
        <div className="flex flex-col gap-3">
          <button
            onClick={() => navigate('/wifi-setup')}
            className="w-full rounded-lg bg-primary px-6 py-3 font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            Connect to WiFi
          </button>
          <button
            onClick={handleControlTable}
            className="w-full rounded-lg border border-border bg-muted px-6 py-3 font-medium hover:bg-accent transition-colors"
          >
            Control Table
          </button>
        </div>
        {showUrlHint && (
          <div className="rounded-lg bg-muted p-3 text-sm text-muted-foreground">
            Open your browser and go to:<br />
            <code className="mt-1 inline-block rounded bg-background px-2 py-0.5 text-foreground select-all">
              http://10.42.0.1
            </code>
          </div>
        )}
      </div>
    </div>
  )
}
