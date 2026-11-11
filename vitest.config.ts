import { defineConfig } from "vitest/config";
export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    testTimeout: 15000,
    // Legacy output-verification tests refresh shared reviewed PDF fixtures.
    // Concurrent readers can otherwise observe a partially written PDF.
    fileParallelism: false,
  },
});
