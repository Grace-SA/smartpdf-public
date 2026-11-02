import { defineConfig } from "vite";
export default defineConfig({
  worker: { format: "es" },
  build: { target: "es2023", manifest: true },
  server: {
    proxy: {
      "/api/word": process.env.WORD_API_TARGET || "http://127.0.0.1:4268",
    },
  },
  preview: {
    proxy: {
      "/api/word": process.env.WORD_API_TARGET || "http://127.0.0.1:4268",
    },
  },
});
