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
    // The default per-test timeout is 5000ms, but setup.ts raises Testing
    // Library's asyncUtilTimeout (to 20000ms) so `waitFor`/`findBy*` can keep
    // retrying through a slow-CI debounce/re-fetch settle when the heavy Editor
    // test worker is CPU-starved by the parallel run. Those two must not fight:
    // an async retry inside a shorter test timeout is killed first ("Test timed
    // out in 5000ms") before it can succeed — exactly the flake that reddened
    // main's frontend CI on unrelated merges. Keep the per-test/hook ceiling a
    // comfortable margin above asyncUtilTimeout so the retry can run to its
    // budget; the retry still stops early on success, so a passing test is
    // never slowed.
    testTimeout: 30000,
    hookTimeout: 30000,
  },
});
