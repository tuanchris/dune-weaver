import { useNavigate } from 'react-router-dom'

export function CaptivePortalPage() {
  const navigate = useNavigate()

  const handleControlTable = () => {
    // Mark that user chose to use the app via hotspot, so Layout stops redirecting back here
    sessionStorage.setItem('captive-dismissed', '1')
    navigate('/')
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
      </div>
    </div>
  )
}
