import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true, // listen on 0.0.0.0 so the dev server is reachable from outside the container
    port: 5173,
    strictPort: true,
    watch: { usePolling: true }, // file changes from a Windows bind mount don't trigger inotify
  },
})
