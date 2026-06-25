import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: proxy API + SSE sang FastAPI (8000). Build: ra dist/ cho FastAPI serve.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/chat': { target: 'http://localhost:8000', changeOrigin: true },
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/session': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
