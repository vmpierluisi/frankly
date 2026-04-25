import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In Docker the backend is reachable via the service name; locally it's localhost.
const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    watch: {
      // Docker bind mounts on macOS need polling for HMR to fire reliably.
      usePolling: true,
      interval: 200,
    },
    // Proxy API calls to the FastAPI backend so there are no CORS issues in dev.
    // The browser talks to Vite (same origin); Vite forwards to the backend.
    proxy: {
      "/candidates": backendUrl,
      "/companies": backendUrl,
      "/templates": backendUrl,
      "/matches": backendUrl,
      "/health": backendUrl,
    },
  },
});
