import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import { Layout } from '@/components/layout/Layout'
import { Toaster } from '@/components/ui/sonner'
import { TableProvider } from '@/contexts/TableContext'
import { UpdatePrompt } from '@/components/UpdatePrompt'

const BrowsePage = lazy(() =>
  import('@/pages/BrowsePage').then((m) => ({ default: m.BrowsePage }))
)
const PlaylistsPage = lazy(() =>
  import('@/pages/PlaylistsPage').then((m) => ({ default: m.PlaylistsPage }))
)
const TableControlPage = lazy(() =>
  import('@/pages/TableControlPage').then((m) => ({ default: m.TableControlPage }))
)
const LEDPage = lazy(() =>
  import('@/pages/LEDPage').then((m) => ({ default: m.LEDPage }))
)
const SettingsPage = lazy(() =>
  import('@/pages/SettingsPage').then((m) => ({ default: m.SettingsPage }))
)
const WiFiSetupPage = lazy(() =>
  import('@/pages/WiFiSetupPage').then((m) => ({ default: m.WiFiSetupPage }))
)
const CaptivePortalPage = lazy(() =>
  import('@/pages/CaptivePortalPage').then((m) => ({ default: m.CaptivePortalPage }))
)
const SetupPage = lazy(() =>
  import('@/pages/SetupPage').then((m) => ({ default: m.SetupPage }))
)

function PageFallback() {
  return (
    <div className="flex items-center justify-center min-h-[50vh] text-muted-foreground">
      <span aria-hidden="true" className="material-icons-outlined text-2xl animate-spin">
        sync
      </span>
      <span className="sr-only">Loading…</span>
    </div>
  )
}

function App() {
  return (
    <TableProvider>
      <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<BrowsePage />} />
            <Route path="playlists" element={<PlaylistsPage />} />
            <Route path="table-control" element={<TableControlPage />} />
            <Route path="led" element={<LEDPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="wifi-setup" element={<WiFiSetupPage />} />
            <Route path="captive" element={<CaptivePortalPage />} />
            <Route path="setup" element={<SetupPage />} />
          </Route>
        </Routes>
      </Suspense>
      <Toaster position="top-center" richColors closeButton />
      <UpdatePrompt />
    </TableProvider>
  )
}

export default App
