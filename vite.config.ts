import { defineConfig } from "vite";
export default defineConfig({
  worker: { format: "es" },
  build: { target: "es2023", manifest: true },
  server: {
    proxy: {
      "/api/pdf-to-excel": {
        target: process.env.PDF_EXCEL_API_TARGET || "http://127.0.0.1:4290",
        changeOrigin: false,
      },
      "/api/ppt": process.env.PPT_API_TARGET || "http://127.0.0.1:4281",
      "/api/excel": process.env.WORD_API_TARGET || "http://127.0.0.1:4268",
      "/api/word": process.env.WORD_API_TARGET || "http://127.0.0.1:4268",
    },
  },
  preview: {
    proxy: {
      "/api/pdf-to-excel": {
        target: process.env.PDF_EXCEL_API_TARGET || "http://127.0.0.1:4290",
        changeOrigin: false,
      },
      "/api/ppt": process.env.PPT_API_TARGET || "http://127.0.0.1:4281",
      "/api/excel": process.env.WORD_API_TARGET || "http://127.0.0.1:4268",
      "/api/word": process.env.WORD_API_TARGET || "http://127.0.0.1:4268",
    },
  },
});
