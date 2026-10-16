import { test, expect, afterEach, vi } from "vitest";
import {
  archiveName,
  dimensions,
  imageName,
  selectedPages,
} from "../src/raster/model";
import { density } from "../src/raster/density";
import { zipFiles } from "../src/downloads/zip";
import { encodeImage, exportImages } from "../src/raster/service";
import type { Engine, Preview } from "../src/platform/engine";
afterEach(() => vi.unstubAllGlobals());
test("all selected geometry is checked before any image is allocated", async () => {
  const dispose = vi.fn(async () => {});
  const preview = {
    dispose,
    doc: {
      numPages: 2,
      getPage: async (n: number) => ({
        getViewport: () => ({ width: n === 2 ? 5000 : 100, height: 100 }),
        cleanup: () => {},
      }),
    },
  } as unknown as Preview;
  const engine = { open: async () => preview } as unknown as Engine;
  await expect(
    exportImages(
      engine,
      new File(["synthetic"], "test.pdf"),
      [0, 1],
      150,
      "jpg",
      new AbortController().signal,
      () => {},
    ),
  ).rejects.toThrow("too large");
  expect(dispose).toHaveBeenCalledOnce();
});
test("image dimensions keep intended integers and enforce device budgets", () => {
  expect(dimensions(3750.0000000000005, 2500)).toEqual({
    width: 3750,
    height: 2500,
  });
  expect(dimensions(2480.3, 3507.8)).toEqual({ width: 2481, height: 3508 });
  for (const [w, h] of [
    [0, 1],
    [NaN, 1],
    [Infinity, 2],
    [4097, 1],
    [4096, 4096],
  ])
    expect(() => dimensions(w!, h!)).toThrow();
});
test("range is unique source order; invalid or empty ranges fail", () => {
  expect(selectedPages("5, 1–3, 2", 5)).toEqual([0, 1, 2, 4]);
  expect(selectedPages(null, 200)).toHaveLength(200);
  for (const s of ["", "0", "6", "2-1", "1,,2"])
    expect(() => selectedPages(s, 5)).toThrow();
});
test("filenames retain source page identity and never ZIP paths", () => {
  expect(imageName("a.pdf", 3, "jpg")).toBe("a-page-003.jpg");
  expect(imageName("合同.pdf", 200, "png")).toBe("合同-page-200.png");
  expect(archiveName("../a.pdf")).not.toMatch(/[/\\]/);
});
test("native encoder null, wrong MIME and cancellation cannot succeed", async () => {
  const fake = (blob: Blob | null) =>
    ({ toBlob: (f: BlobCallback) => f(blob) }) as HTMLCanvasElement;
  for (const blob of [null, new Blob(["x"], { type: "image/png" })])
    await expect(
      encodeImage(fake(blob), "image/jpeg", new AbortController().signal),
    ).rejects.toThrow();
  const c = new AbortController();
  let finish: BlobCallback = () => {};
  const p = encodeImage(
    {
      toBlob: (f: BlobCallback) => {
        finish = f;
      },
    } as HTMLCanvasElement,
    "image/png",
    c.signal,
  );
  const rejected = expect(p).rejects.toThrow("Cancelled");
  c.abort();
  finish(new Blob(["x"], { type: "image/png" }));
  await rejected;
});
test("DPI changes JFIF density without altering scan payload", async () => {
  const source = new Uint8Array([255, 216, 255, 218, 0, 2, 9, 8, 7, 255, 217]);
  const out = new Uint8Array(
    await (
      await density(new Blob([source], { type: "image/jpeg" }), 300)
    ).arrayBuffer(),
  );
  expect([...out.slice(20)]).toEqual([...source.slice(2)]);
  expect(out[13]).toBe(1);
  expect(new DataView(out.buffer).getUint16(14)).toBe(300);
  await expect(
    density(new Blob(["x"], { type: "image/png" }), 150),
  ).rejects.toThrow();
});
class Reader {
  result: ArrayBuffer | null = null;
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  abort() {
    this.onabort?.();
  }
  readAsArrayBuffer(blob: Blob) {
    void blob.arrayBuffer().then((value) => {
      this.result = value;
      this.onload?.();
    });
  }
}
test("ZIP supports explicit 200 images, CRC and exact header budget; default limit stays 50", async () => {
  vi.stubGlobal("FileReader", Reader);
  const files = Array.from(
    { length: 200 },
    (_, i) =>
      new File([`page ${i}`], `page-${String(i + 1).padStart(3, "0")}.jpg`),
  );
  await expect(zipFiles(files)).rejects.toThrow();
  const zip = await zipFiles(files, { maxFiles: 200 });
  const bytes = await zip.arrayBuffer(),
    view = new DataView(bytes);
  expect(view.getUint32(0, true)).toBe(0x04034b50);
  expect(view.getUint16(bytes.byteLength - 12, true)).toBe(200);
  await expect(
    zipFiles(files, { maxFiles: 200, maxBytes: zip.size - 1 }),
  ).rejects.toThrow();
  const c = new AbortController();
  c.abort();
  await expect(
    zipFiles(files, { maxFiles: 200, signal: c.signal }),
  ).rejects.toThrow(/cancel/i);
});
