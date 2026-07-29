import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Windows bind mounts do not forward inotify events into the container.
    watch: { usePolling: true },
    // The browser only ever talks to one origin, so there is no CORS to configure
    // and no API base URL baked into the bundle.
    proxy: {
      '/api': { target: 'http://backend:8000', changeOrigin: true },
    },
  },
})
