import { test, expect, vi } from "vitest";
import { PDFDocument, PDFName } from "pdf-lib";
import { writeFile } from "node:fs/promises";
import { deflateSync } from "node:zlib";
import { randomBytes } from "node:crypto";
import { checkFlateImage } from "../src/core/stream-image-check";
import { probePdf } from "../src/core/probe";

for (const overLimit of [false, true])
  test(`stream reader releases its lock and cancels only unfinished work (limit: ${overLimit})`, async () => {
    const reader = {
      read: vi
        .fn()
        .mockResolvedValueOnce({ done: false, value: new Uint8Array(10) })
        .mockResolvedValueOnce({ done: true }),
      cancel: vi.fn().mockResolvedValue(undefined),
      releaseLock: vi.fn(),
    };
    const pipe = vi
      .spyOn(ReadableStream.prototype, "pipeThrough")
      .mockReturnValue({
        getReader: () => reader,
      } as unknown as ReadableStream);
    try {
      const pending = checkFlateImage(
        deflateSync(Buffer.alloc(10)),
        overLimit ? 5 : 20,
      );
      if (overLimit)
        await expect(pending).rejects.toMatchObject({ code: "RESOURCE_LIMIT" });
      else expect(await pending).toBe(10);
      expect(reader.cancel).toHaveBeenCalledTimes(overLimit ? 1 : 0);
      expect(reader.releaseLock).toHaveBeenCalledOnce();
    } finally {
      pipe.mockRestore();
    }
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
test("older runtimes retain the bounded decoder fallback", async () => {
  const bytes = await images(12);
  vi.stubGlobal("DecompressionStream", undefined);
  try {
    expect(await probePdf(bytes, "preview")).toMatchObject({
      ok: false,
      code: "RESOURCE_LIMIT",
    });
  } finally {
    vi.unstubAllGlobals();
  }
});
