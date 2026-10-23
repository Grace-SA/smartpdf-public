import { it, expect, vi, afterEach } from "vitest";
import { readFile } from "node:fs/promises";

const font = await readFile(
  "public/number-fonts/SmartPDFNumberSans-Regular.ttf",
);
afterEach(() => vi.unstubAllGlobals());
async function loader() {
  vi.resetModules();
  return (await import("../src/numbers/font")).prepareNumberFont;
}
function valid() {
  return new Response(new Uint8Array(font), { status: 200 });
}

it("caches only one validated same-origin font", async () => {
  const fetch = vi.fn().mockResolvedValue(valid());
  vi.stubGlobal("fetch", fetch);
  const prepare = await loader(),
    signal = new AbortController().signal;
  const [a, b] = await Promise.all([prepare(signal), prepare(signal)]);
  expect(a).toBe(b);
  expect(a.byteLength).toBe(10248);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0]![0]).toBe(
    "/number-fonts/SmartPDFNumberSans-Regular.ttf",
  );
});
it("rejects corrupt 200 responses and fetches a fresh valid font on retry", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response("synthetic broken font"))
    .mockResolvedValueOnce(valid());
  vi.stubGlobal("fetch", fetch);
  const prepare = await loader(),
    signal = new AbortController().signal;
  await expect(prepare(signal)).rejects.toThrow();
  await expect(prepare(signal)).resolves.toHaveLength(10248);
  expect(fetch).toHaveBeenCalledTimes(2);
});
it("does not cache failed network responses", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response(null, { status: 503 }))
    .mockResolvedValueOnce(valid());
  vi.stubGlobal("fetch", fetch);
  const prepare = await loader(),
    signal = new AbortController().signal;
  await expect(prepare(signal)).rejects.toThrow(/could not load/);
  await expect(prepare(signal)).resolves.toHaveLength(10248);
});
it("refuses an oversized font before parsing and retains a working retry", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response(new Uint8Array(65537)))
    .mockResolvedValueOnce(valid());
  vi.stubGlobal("fetch", fetch);
  const prepare = await loader(),
    signal = new AbortController().signal;
  await expect(prepare(signal)).rejects.toThrow(/budget/);
  await expect(prepare(signal)).resolves.toHaveLength(10248);
});
