import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    host: true,
    // Allow Cloudflared quick tunnel hostnames to reach the dev server.
    allowedHosts: ['odoo-ocr.cuhk.digital'],
    strictPort: true,
    // Critical for Cloudflare Tunnels to handle Hot Module Replacement
    hmr: {
      protocol: 'wss',
      clientPort: 443,
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: '../backend/static',
    emptyOutDir: true,
    // Vite 8 standardizes on rolldownOptions; keep chunking behavior unchanged.
    rolldownOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes('pdfjs-dist')) return 'pdf'
          if (id.includes('node_modules') && 
             (id.includes('vue') || id.includes('pinia'))) {
            return 'vendor'
          }
        },
      },
    },
  },
})
