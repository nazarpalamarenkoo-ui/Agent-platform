import path from "node:path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8000"

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
  },
  server: {
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
        rewrite: (requestPath) => requestPath.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./tests/setup.ts",
    include: ["tests/**/*.test.{ts,tsx}"],
    css: false,
  },
})