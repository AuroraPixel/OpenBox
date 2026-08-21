import { defineConfig } from "vitest/config"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import path from "node:path"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  build: {
    target: "es2022",
    // No manual chunk groups: xterm and the markdown stack are only ever
    // reached through dynamic import(), so Rolldown splits them naturally.
    // (Grouping them by regex pulled shared React into the vendor chunk and
    // dragged it onto the first screen — measured, not hypothetical.)
  },
  server: {
    // Port 3000 matches the redirect URI registered in Logto
    // (http://localhost:3000/callback) — changing it means re-registering there.
    host: "0.0.0.0",
    port: 3000,
    strictPort: true,
    proxy: {
      "/api": "http://localhost:8080",
      "/ws": { target: "ws://localhost:8080", ws: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    include: ["src/**/*.test.{ts,tsx}"],
  },
})
