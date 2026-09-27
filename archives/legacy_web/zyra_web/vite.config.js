import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: true,
    proxy: {
      '/api': 'http://127.0.0.1:5000',
      '/live_tasks': 'http://127.0.0.1:5000'
    }
  }
})
