import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The SPA is served by FastAPI under /static/app/ in production, and built into
// ../dist (which is committed to git so Python-only contributors need no Node).
//
// In `nb web --dev`, the Click command launches `npm run dev` (Vite on 5173) and
// uvicorn on the chosen port; Vite proxies /api and /ws back to uvicorn. The
// target port is passed in via VITE_API_TARGET (defaults to the nb web default).
const apiTarget = process.env.VITE_API_TARGET || "http://127.0.0.1:3000";

export default defineConfig({
  plugins: [react()],
  base: "/static/app/",
  build: {
    outDir: "../dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
      "/ws": { target: apiTarget, ws: true, changeOrigin: true },
    },
  },
});
