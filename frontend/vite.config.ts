import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: parseInt(process.env.PORT || '5173'),
    proxy: {
      // WebSocket endpoints
      '/ws': {
        target: 'ws://localhost:8080',
        ws: true,
        // Suppress connection reset errors (common during backend restarts)
        configure: (proxy, _options) => {
          // Handle proxy errors silently for expected connection issues
          const handleError = (err: Error) => {
            const msg = err.message || ''
            if (msg.includes('ECONNRESET') || msg.includes('ECONNREFUSED') || msg.includes('EPIPE')) {
              return // Silently ignore
            }
            console.error('WebSocket proxy error:', msg)
          }
          proxy.on('error', handleError)
          proxy.on('proxyReqWs', (_proxyReq, _req, socket) => {
            socket.on('error', handleError)
          })
        },
      },
      // API endpoints - proxy all backend routes
      '/send_home': 'http://localhost:8080',
      '/send_coordinate': 'http://localhost:8080',
      '/stop_execution': 'http://localhost:8080',
      '/move_to_center': 'http://localhost:8080',
      '/move_to_perimeter': 'http://localhost:8080',
      '/set_speed': 'http://localhost:8080',
      '/run_theta_rho': 'http://localhost:8080',
      '/pause_execution': 'http://localhost:8080',
      '/resume_execution': 'http://localhost:8080',
      '/serial_status': 'http://localhost:8080',
      '/connect': 'http://localhost:8080',
      '/disconnect': 'http://localhost:8080',
      '/get_speed': 'http://localhost:8080',
      '/list_theta_rho_files': 'http://localhost:8080',
      '/list_theta_rho_files_with_metadata': 'http://localhost:8080',
      '/list_all_playlists': 'http://localhost:8080',
      '/get_playlist': 'http://localhost:8080',
      '/create_playlist': 'http://localhost:8080',
      '/modify_playlist': 'http://localhost:8080',
      '/delete_playlist': 'http://localhost:8080',
      '/rename_playlist': 'http://localhost:8080',
      '/run_playlist': 'http://localhost:8080',
      '/add_to_playlist': 'http://localhost:8080',
      '/preview_thr': 'http://localhost:8080',
      '/preview_thr_batch': 'http://localhost:8080',
      '/preview': 'http://localhost:8080',
      '/get_theta_rho_coordinates': 'http://localhost:8080',
      '/get_led_config': 'http://localhost:8080',
      '/set_led_config': 'http://localhost:8080',
      '/api': 'http://localhost:8080',
      '/restart': 'http://localhost:8080',
      '/static': 'http://localhost:8080',
    },
  },
  build: {
    outDir: '../static/dist',
    emptyOutDir: true,
  },
})
