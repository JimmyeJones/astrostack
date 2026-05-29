import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Build output goes straight into the Python package so FastAPI can serve it.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../webapp/static",
    emptyOutDir: true,
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
