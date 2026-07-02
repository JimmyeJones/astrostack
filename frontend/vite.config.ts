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
  },
});
