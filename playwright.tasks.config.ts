import base from "./playwright.ux.config";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  ...base,
  testMatch: [
    "task-boundaries.spec.ts",
    "ux-leave.spec.ts",
    "ux-preview-stability.spec.ts",
    "ux-production.spec.ts",
    "ux-feedback.spec.ts",
    "ux-review-fixes.spec.ts",
  ],
  // Replaced by task-boundaries: these historical tests assert removed global
  // history, implicit reuse, and the old continuation dialog.
  grepInvert:
    /split ranges, download ZIP, child edit, undo and source retention|photo generated source, merge to five pages|continuation dialog stays centered/,
  reporter: [
    ["list"],
    ["json", { outputFile: "docs/evidence/ux10-regression.json" }],
  ],
});
