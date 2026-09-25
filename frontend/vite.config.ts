import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// VITE_BASE is set to "/<repo>/" by the GitHub Pages workflow; "/" everywhere else.
export default defineConfig({
  base: process.env.VITE_BASE ?? "/",
  plugins: [react()],
  server: { port: 5173 },
  build: { chunkSizeWarningLimit: 900 },
});
