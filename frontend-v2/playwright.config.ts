import { defineConfig } from "@playwright/test"

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  // Serial: specs share one dev account and the backend rate-limits login.
  workers: 1,
  use: {
    baseURL: "http://localhost:3000",
    // Use the full chromium in new-headless mode; the separate
    // headless-shell download stalls on this network.
    channel: "chromium",
    locale: "zh-CN",
  },
  projects: [
    { name: "setup", testMatch: /auth\.setup\.ts/ },
    {
      name: "main",
      testMatch: /.*\.spec\.ts/,
      dependencies: ["setup"],
      use: { storageState: "test-results/.auth-state.json" },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 30_000,
  },
})
