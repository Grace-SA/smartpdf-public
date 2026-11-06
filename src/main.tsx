import { createRoot } from "react-dom/client";
import { App } from "./App";
import { WordBoundary } from "./word/WordBoundary";
import { WordEntry } from "./word/WordEntry";
import { ExcelEntry } from "./excel/ExcelEntry";
import "./style.css";
import "./product.css";
import "./interaction.css";

if (["smartpdf.com.au", "www.smartpdf.com.au"].includes(location.hostname)) {
  const beacon = document.createElement("script");
  beacon.defer = true;
  beacon.src = "https://static.cloudflareinsights.com/beacon.min.js";
  beacon.dataset.cfBeacon = JSON.stringify({
    token: "38a576658b4646609d93f5681182fd88",
  });
  document.head.append(beacon);
}

createRoot(document.getElementById("root")!).render(
  (!import.meta.env.PROD || import.meta.env.VITE_ENABLE_EXCEL === "true") &&
    /^\/excel-to-pdf\/?$/.test(location.pathname) ? (
    <WordBoundary title="Excel to PDF">
      <ExcelEntry />
    </WordBoundary>
  ) : /^\/word-to-pdf\/?$/.test(location.pathname) ? (
    <WordBoundary>
      <WordEntry />
    </WordBoundary>
  ) : (
    <App />
  ),
);
