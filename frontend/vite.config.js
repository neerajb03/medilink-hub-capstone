import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Internal ALB DNS for backend routing (set by launch template user-data on AWS)
// Locally falls back to localhost with direct service ports
let INTERNAL_ALB = process.env.INTERNAL_ALB_DNS || 'http://localhost'

// Safety check: if the env var was set without http://, the Vite proxy will crash
// with "Cannot read properties of null (reading 'split')"
if (!INTERNAL_ALB.startsWith('http')) {
  INTERNAL_ALB = `http://${INTERNAL_ALB}`
}

const IS_AWS = !!process.env.INTERNAL_ALB_DNS || INTERNAL_ALB.includes('amazonaws.com')

// Helper: create proxy config that only proxies API calls (XHR/fetch),
// not browser page navigations. This lets React Router handle SPA routes
// while still proxying AJAX calls to the backend.
function apiProxy(target) {
  return {
    target,
    changeOrigin: true,
    // If the browser is navigating to this path (Accept: text/html),
    // serve the SPA instead of proxying to the backend
    bypass(req) {
      if (req.headers.accept && req.headers.accept.includes('text/html')) {
        return '/index.html'
      }
    }
  }
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    allowedHosts: ['.amazonaws.com', 'localhost'],
    proxy: {
      // User service routes
      '/register': apiProxy(IS_AWS ? `${INTERNAL_ALB}` : `${INTERNAL_ALB}:8001`),
      '/login': apiProxy(IS_AWS ? `${INTERNAL_ALB}` : `${INTERNAL_ALB}:8001`),
      '/me': apiProxy(IS_AWS ? `${INTERNAL_ALB}` : `${INTERNAL_ALB}:8001`),
      // Appointment service routes
      '/appointments': apiProxy(IS_AWS ? `${INTERNAL_ALB}` : `${INTERNAL_ALB}:8002`),
      // Health records service routes
      '/records': apiProxy(IS_AWS ? `${INTERNAL_ALB}` : `${INTERNAL_ALB}:8003`),
      // Document service routes
      '/documents': apiProxy(IS_AWS ? `${INTERNAL_ALB}` : `${INTERNAL_ALB}:8004`),
    }
  }
})

