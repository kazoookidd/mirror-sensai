import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const API_SERVER = process.env.SENSAI_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": API_SERVER },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  test: {
    environmentMatchGlobs: [["**/*.test.jsx", "jsdom"]],
    restoreMocks: true,
  },
});
