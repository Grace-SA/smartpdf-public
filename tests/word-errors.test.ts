import { afterEach, expect, it, vi } from "vitest";
import { responseFailure, wordFailure, wordRequest } from "../src/word/errors";
import { substitutedFontDeclarations } from "../src/word/font-policy";
afterEach(() => vi.unstubAllGlobals());
it("distinguishes queue, input, session and output failures", () => {
  expect(responseFailure(429).code).toBe("QUEUE_FULL");
  expect(responseFailure(415).code).toBe("INPUT_TYPE");
  expect(responseFailure(413).message).toContain("30 MiB");
  expect(responseFailure(403).code).toBe("SESSION_EXPIRED");
  expect(responseFailure(401).code).toBe("SESSION_EXPIRED");
  expect(responseFailure(410).code).toBe("TASK_EXPIRED");
  expect(wordFailure("OUTPUT_INVALID")).toContain("not offered for download");
  expect(wordFailure("INPUT_VIEW_PREPARATION_FAILED")).toContain("Word");
});
it("handles HTML proxy errors and network loss without a JSON parsing error", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(new Response("upstream unavailable", { status: 503 })),
  );
  await expect(wordRequest("/api/word/jobs")).rejects.toMatchObject({
    code: "SERVICE_UNAVAILABLE",
    status: 503,
  });
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed")));
  await expect(wordRequest("/api/word/jobs")).rejects.toMatchObject({
    code: "NETWORK",
  });
});
it("preserves cancellation and does not turn it into a connection failure", async () => {
  const abort = new AbortController();
  abort.abort();
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(abort.signal.reason));
  await expect(
    wordRequest("/api/word/jobs", { signal: abort.signal }),
  ).rejects.toBe(abort.signal.reason);
});
it("warns about declared unavailable fonts without rejecting otherwise supported input", () => {
  expect(
    substitutedFontDeclarations([
      "Noto Sans CJK SC",
      "carlito",
      "Calibri",
      "SimSun",
    ]),
  ).toEqual(["Calibri", "SimSun"]);
});
