import { defineConfig } from 'vitest/config'
import solid from 'vite-plugin-solid'

export default defineConfig({
  plugins: [solid()],
  server: {
    port: 3020,
    // The browser talks to Vite only; Vite forwards /api to the backend (no CORS in development).
    proxy: {
      '/api': { target: 'http://localhost:8020', changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
  },
  resolve: {
    // Solid ships separate server/browser builds; tests must use the browser one.
    conditions: ['development', 'browser'],
  },
})
