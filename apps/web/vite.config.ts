import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API proxy target is overridable so a second checkout (or CI) can run
// its own backend on a non-default port: MESH2PARAM_API_PROXY=http://127.0.0.1:8001
const apiProxy = process.env["MESH2PARAM_API_PROXY"] ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": apiProxy,
      "/health": apiProxy,
      "/ready": apiProxy,
    },
  },
  build: {
    target: "es2022",
    sourcemap: false,
  },
});
