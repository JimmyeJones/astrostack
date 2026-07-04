import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Build output goes straight into the Python package so FastAPI can serve it.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../webapp/static",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // Split the big, rarely-changing vendor libraries out of the main app
        // chunk so the browser caches them across app deploys and no single
        // eager chunk trips the 500 kB warning. Route code (and the lazy
        // Sky/aladin atlas) keep their own chunks.
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          mantine: ["@mantine/core", "@mantine/hooks", "@mantine/notifications"],
          query: ["@tanstack/react-query"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
    // Run test files sequentially (one at a time) rather than in parallel
    // workers. Root cause of the recurring frontend-CI flake: the heavy
    // Editor.test.tsx spins up many full-app renders, and when several test-file
    // workers run at once on a small CI runner its worker gets CPU-starved — a
    // `findBy*`/`waitFor` that settles sub-second when scheduled instead drags
    // past 10s (v0.69.19 measured 10534ms), and any *synchronous* assertion right
    // after it races the lagging render — so multiple Editor tests intermittently
    // reddened `main` with "unable to find element" timeouts, even though the code
    // was fine and the suite passed locally. Serialising the files gives each the
    // full CPU (whole suite ~65s vs ~27s parallel — a fine trade for a reliably
    // green gate) so no worker starves and the timeouts below are never
    // approached. The raised ceilings stay as a safety net.
    fileParallelism: false,
    // The default per-test timeout is 5000ms, but setup.ts raises Testing
    // Library's asyncUtilTimeout (to 20000ms) so `waitFor`/`findBy*` can keep
    // retrying through a slow-CI debounce/re-fetch settle. Those two must not
    // fight: an async retry inside a shorter test timeout is killed first ("Test
    // timed out in 5000ms") before it can succeed. Keep the per-test/hook ceiling
    // a comfortable margin above asyncUtilTimeout so the retry can run to its
    // budget; the retry still stops early on success, so a passing test is
    // never slowed.
    testTimeout: 30000,
    hookTimeout: 30000,
  },
});
