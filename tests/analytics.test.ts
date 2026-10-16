import { describe, expect, it } from "vitest";
import { analyticsReason, buildAnalyticsPayload } from "../src/analytics";

describe("privacy-conscious analytics", () => {
  it("emits only allow-listed coarse fields", () => {
    const payload = buildAnalyticsPayload("process_success", "compress", {
      fileCount: 3,
      totalBytes: 7.2 * 1024 * 1024,
      pages: 42,
      durationMs: 2400,
    });
    expect(payload).toEqual({
      schema: 1,
      event: "process_success",
      tool: "compress",
      file_count: "<=5",
      size_mib: "<=10",
      pages: "<=50",
      duration_ms: "<=3000",
      reason: undefined,
    });
    expect(JSON.stringify(payload)).not.toMatch(
      /name|url|document|user|account/i,
    );
  });

  it("maps errors to stable aggregate categories", () => {
    expect(analyticsReason(new Error("Password protected PDF"))).toBe(
      "unsupported",
    );
    expect(analyticsReason(new DOMException("Aborted", "AbortError"))).toBe(
      "cancelled",
    );
    expect(analyticsReason(new Error("Worker stopped"))).toBe("worker");
  });
});
