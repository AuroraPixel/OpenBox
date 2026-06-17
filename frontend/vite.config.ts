import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    target: "esnext",
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-xterm": ["@xterm/xterm", "@xterm/addon-fit", "@xterm/addon-web-links"],
          "vendor-markdown": ["react-markdown", "remark-gfm", "rehype-highlight"],
          "vendor-diff": ["react-diff-viewer-continued"],
          "vendor-motion": ["framer-motion"],
        },
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/api': 'http://localhost:8080',
      '/ws': {
        target: 'ws://localhost:8080',
        ws: true,
      },
    },
  },
})
