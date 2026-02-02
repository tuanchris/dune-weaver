import { Routes, Route } from 'react-router-dom'
import { Layout } from '@/components/layout/Layout'
import { BrowsePage } from '@/pages/BrowsePage'
import { PlaylistsPage } from '@/pages/PlaylistsPage'
import { TableControlPage } from '@/pages/TableControlPage'
import { LEDPage } from '@/pages/LEDPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { Toaster } from '@/components/ui/sonner'
import { TableProvider } from '@/contexts/TableContext'

function App() {
  return (
    <TableProvider>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<BrowsePage />} />
          <Route path="playlists" element={<PlaylistsPage />} />
          <Route path="table-control" element={<TableControlPage />} />
          <Route path="led" element={<LEDPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
      <Toaster position="top-center" richColors closeButton />
    </TableProvider>
  )
}

export default App
