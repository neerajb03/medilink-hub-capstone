import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Internal ALB DNS for backend routing (set by launch template user-data on AWS)
// Locally falls back to localhost with direct service ports
const INTERNAL_ALB = process.env.INTERNAL_ALB_DNS || 'http://localhost'
const IS_AWS = !!process.env.INTERNAL_ALB_DNS

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    allowedHosts: true,
    proxy: {
      // User service routes
      '/register':     { target: IS_AWS ? `${INTERNAL_ALB}` : `${INTERNAL_ALB}:8001`, changeOrigin: true },
      '/login':        { target: IS_AWS ? `${INTERNAL_ALB}` : `${INTERNAL_ALB}:8001`, changeOrigin: true },
      '/me':           { target: IS_AWS ? `${INTERNAL_ALB}` : `${INTERNAL_ALB}:8001`, changeOrigin: true },
      // Appointment service routes
      '/appointments': { target: IS_AWS ? `${INTERNAL_ALB}` : `${INTERNAL_ALB}:8002`, changeOrigin: true },
      // Health records service routes
      '/records':      { target: IS_AWS ? `${INTERNAL_ALB}` : `${INTERNAL_ALB}:8003`, changeOrigin: true },
      // Document service routes
      '/documents':    { target: IS_AWS ? `${INTERNAL_ALB}` : `${INTERNAL_ALB}:8004`, changeOrigin: true },
    }
  }
})
