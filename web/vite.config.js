import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  publicDir: 'public',
  server: {
    proxy: {
      '/api': 'http://localhost:8080'
    }
  },
  build: {
    assetsDir: 'assets',
    copyPublicDir: true
  }
})