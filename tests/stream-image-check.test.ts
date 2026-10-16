import { test, expect, vi } from "vitest";
import { PDFDocument, PDFName } from "pdf-lib";
import { writeFile } from "node:fs/promises";
import { deflateSync } from "node:zlib";
import { randomBytes } from "node:crypto";
import { checkFlateImage } from "../src/core/stream-image-check";
import { probePdf } from "../src/core/probe";

test("bounded validation retains input bytes and needs no native stream implementation", async () => {
  const raw = randomBytes(180_000),
    compressed = deflateSync(raw),
    original = compressed.slice();
  vi.stubGlobal(
    "DecompressionStream",
    class {
      constructor() {
        throw new Error("Synthetic unavailable native stream");
      }
    },
  );
  try {
    expect(await checkFlateImage(compressed)).toBe(raw.length);
    expect(compressed).toEqual(original);
  } finally {
    vi.unstubAllGlobals();
  }
});

test("streamed validation requires the complete zlib terminator and rejects trailing input", async () => {
  const compressed = deflateSync(randomBytes(10_000));
  for (const strip of [1, 2, 4, 7])
    await expect(
      checkFlateImage(compressed.subarray(0, compressed.length - strip)),
    ).rejects.toMatchObject({ code: "INVALID_INPUT" });
  for (const tail of [Buffer.from([0]), Buffer.from([1, 2, 3]), compressed])
    await expect(
      checkFlateImage(Buffer.concat([compressed, tail])),
    ).rejects.toMatchObject({ code: "INVALID_INPUT" });
});

test("image output budget accepts the exact boundary and rejects the next byte", async () => {
  const compressed = deflateSync(Buffer.alloc(100_000, 42));
  expect(await checkFlateImage(compressed, 100_000)).toBe(100_000);
  await expect(checkFlateImage(compressed, 99_999)).rejects.toMatchObject({
    code: "RESOURCE_LIMIT",
  });
  expect(await checkFlateImage(deflateSync(Buffer.alloc(0)))).toBe(0);
});

test("understated zlib windows retain full-window compatibility without skipping checksum validation", async () => {
  const seed = randomBytes(10000),
    input = Buffer.concat([seed, seed, seed]);
  const bytes = deflateSync(input);
  bytes[0] = 0x58;
  bytes[1] = 0;
  bytes[1] = (31 - (0x5800 % 31)) % 31;
  expect(await checkFlateImage(bytes)).toBe(input.length);
  bytes[bytes.length - 1] = bytes[bytes.length - 1]! ^ 1;
  await expect(checkFlateImage(bytes)).rejects.toBeDefined();
});

async function images(count: number) {
  const d = await PDFDocument.create();
  d.addPage();
  const bytes = deflateSync(Buffer.alloc(12 * 1024 * 1024, 240));
  for (let i = 0; i < count; i++)
    d.context.register(
      d.context.stream(bytes, {
        Type: "XObject",
        Subtype: "Image",
        Width: 4096,
        Height: 1024,
        ColorSpace: "DeviceRGB",
        BitsPerComponent: 8,
        Filter: "FlateDecode",
      }),
    );
  return d.save();
}

test("many separate lossless images validate without accumulating full raster buffers", async () => {
  expect((await probePdf(await images(12), "preview")).ok).toBe(true);
});

test("a visible multipage scan exercises streamed work beyond the old cumulative allocation limit", async () => {
  const d = await PDFDocument.create();
  const pixels = Buffer.alloc(4096 * 3072, 240);
  for (let i = 0; i < pixels.length; i += 4096 * 200)
    pixels.fill(64, i, Math.min(i + 4096 * 50, pixels.length));
  for (let i = 0; i < 12; i++) {
    const p = d.addPage([400, 300]);
    const image = d.context.register(
      d.context.flateStream(pixels, {
        Type: "XObject",
        Subtype: "Image",
        Width: 4096,
        Height: 3072,
        ColorSpace: "DeviceGray",
        BitsPerComponent: 8,
      }),
    );
    p.node.set(
      PDFName.of("Resources"),
      d.context.obj({ XObject: { Scan: image } }),
    );
    p.node.set(
      PDFName.of("Contents"),
      d.context.register(
        d.context.flateStream("q 400 0 0 300 0 0 cm /Scan Do Q"),
      ),
    );
  }
  const bytes = await d.save();
  expect((await probePdf(bytes, "combine")).ok).toBe(true);
  await writeFile("tests/fixtures/combine/final-stream-scan.pdf", bytes);
});
test("stream validation enforces the image limit, remaining work and corrupt-stream rejection", async () => {
  await expect(
    checkFlateImage(deflateSync(Buffer.alloc(33 * 1024 * 1024))),
  ).rejects.toMatchObject({ code: "RESOURCE_LIMIT" });
  await expect(
    checkFlateImage(deflateSync(Buffer.alloc(8192)), 4096),
  ).rejects.toMatchObject({ code: "RESOURCE_LIMIT" });
  await expect(
    checkFlateImage(new Uint8Array([1, 2, 3])),
  ).rejects.toBeDefined();
});
test("image work is bounded even though image buffers are streamed", async () => {
  expect(await probePdf(await images(43), "preview")).toMatchObject({
    ok: false,
    code: "RESOURCE_LIMIT",
  });
}, 30000);
test("bounded image validation works without native decompression streams", async () => {
  const bytes = await images(12);
  vi.stubGlobal("DecompressionStream", undefined);
  try {
    expect(await probePdf(bytes, "preview")).toMatchObject({ ok: true });
  } finally {
    vi.unstubAllGlobals();
  }
});
