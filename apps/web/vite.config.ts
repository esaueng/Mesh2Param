import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    exclude: ["occt-wasm"],
  },
  worker: {
    format: "es",
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
      "/ready": "http://127.0.0.1:8000",
    },
  },
  build: {
    target: "esnext",
    assetsInlineLimit: 0,
    sourcemap: false,
  },
});
