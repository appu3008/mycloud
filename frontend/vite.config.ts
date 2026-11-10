import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api to the locally-bound backend (loopback only).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
  build: {
    sourcemap: false,
  },
});
