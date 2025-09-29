import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  publicDir: "public",
  build: {
    outDir: "../frontend_dist",
    emptyOutDir: true,
    copyPublicDir: true
  }
});