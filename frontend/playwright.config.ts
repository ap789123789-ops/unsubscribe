import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 20_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  workers: process.env.CI ? 1 : undefined,
  use: {
    baseURL: 'http://127.0.0.1:8000',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run build && cd ../backend && uv run uvicorn tests.e2e_app:app --host 127.0.0.1 --port 8000',
    env: { UV_CACHE_DIR: '/tmp/unsubscribe-uv-cache' },
    url: 'http://127.0.0.1:8000/api/health',
    reuseExistingServer: false,
    timeout: 120_000,
  },
})
