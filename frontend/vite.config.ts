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
    allowedHosts: true, // Allow all hosts for local network development
    proxy: {
      // WebSocket endpoints
      '/ws': {
        target: 'ws://localhost:8080',
        ws: true,
        // Suppress connection errors (common during backend restarts)
        configure: (proxy, _options) => {
          // Handle proxy errors silently for expected connection issues
          const isConnectionError = (err: Error & { code?: string }) => {
            const msg = err.message || ''
            const code = err.code || ''
            // Check error code (most reliable for AggregateError)
            if (['ECONNRESET', 'ECONNREFUSED', 'EPIPE', 'ETIMEDOUT'].includes(code)) {
              return true
            }
            // Check message as fallback
            if (msg.includes('ECONNRESET') || msg.includes('ECONNREFUSED') ||
                msg.includes('EPIPE') || msg.includes('ETIMEDOUT') ||
                msg.includes('AggregateError')) {
              return true
            }
            return false
          }

          const handleError = (err: Error) => {
            if (isConnectionError(err)) {
              return // Silently ignore connection errors
            }
            // Only log unexpected errors
            console.error('WebSocket proxy error:', err.message)
          }

          proxy.on('error', handleError)
          proxy.on('proxyReqWs', (_proxyReq, _req, socket) => {
            socket.on('error', (err) => {
              if (!isConnectionError(err)) {
                console.error('WebSocket socket error:', err.message)
              }
            })
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
      '/skip_pattern': 'http://localhost:8080',
      '/serial_status': 'http://localhost:8080',
      '/list_serial_ports': 'http://localhost:8080',
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
      '/static': 'http://localhost:8080',
    },
  },
  build: {
    outDir: '../static/dist',
    emptyOutDir: true,
  },
})
