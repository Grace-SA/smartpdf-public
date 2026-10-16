import { deflateSync, constants } from "node:zlib";
import { expect, it } from "vitest";
import { inspectInlineImages } from "../src/core/inline-images";
import { PDFDocument, PDFName } from "pdf-lib";
import { writeFile } from "node:fs/promises";
import { combinePdfs } from "../src/combine/generate";
it("a compressed inline raster survives actual generation for device checks", async () => {
  const d = await PDFDocument.create(),
    p = d.addPage([300, 300]),
    raster = Buffer.alloc(32 * 32 * 3, 80);
  const content = Buffer.concat([
    Buffer.from(
      "q 240 0 0 240 30 30 cm BI /W 32 /H 32 /BPC 8 /CS /RGB /F /Fl ID ",
    ),
    deflateSync(raster),
    Buffer.from(" EI Q"),
  ]);
  p.node.set(
    PDFName.of("Contents"),
    d.context.register(d.context.flateStream(content)),
  );
  const bytes = await d.save();
  expect(
    (
      await PDFDocument.load(await combinePdfs([bytes, bytes], () => {}))
    ).getPageCount(),
  ).toBe(2);
  await writeFile("tests/fixtures/combine/final-inline.pdf", bytes);
});
const bytes = (value: string) => new TextEncoder().encode(value);
it("fast ordinary-token scanning still finds escaped MCID names and a later inline image", () => {
  const drawing = "0 0 100 200 re 0.123 0.456 0.789 rg f Q q\n".repeat(20000);
  let mcids = 0;
  expect(
    inspectInlineImages(
      bytes(
        drawing +
          "/Span << /M#43ID 1 >> BDC (BI /MCID) Tj EMC % /MCID\nBI /W 1 /H 1 /BPC 8 /CS /RGB ID abc EI",
      ),
      undefined,
      () => mcids++,
    ),
  ).toBe(0);
  expect(mcids).toBe(1);
  expect(() =>
    inspectInlineImages(
      bytes(drawing + "BI /W 5000 /H 5000 /BPC 8 /CS /RGB ID abc EI"),
    ),
  ).toThrow("RESOURCE_LIMIT");
});
it("ignores image-like text inside strings, comments, hex and arrays", () => {
  expect(() =>
    inspectInlineImages(
      bytes("(BI /W 90000 /H 90000 ID) Tj % BI\n<4249> Tj [(BI)] TJ /BI Do"),
    ),
  ).not.toThrow();
});
it("rejects oversized inline images before consuming pixel data", () => {
  expect(() =>
    inspectInlineImages(bytes("BI /W 5000 /H 5000 /BPC 8 /CS /RGB ID x EI")),
  ).toThrow("RESOURCE_LIMIT");
});
it("accepts an unfiltered 1px RGB inline image with exact byte length", () => {
  expect(() =>
    inspectInlineImages(bytes("BI /W 1 /H 1 /BPC 8 /CS /RGB ID abc EI")),
  ).not.toThrow();
});
it("rejects unknown inline encoding and incomplete data", () => {
  expect(() =>
    inspectInlineImages(bytes("BI /W 1 /H 1 /BPC 8 /CS /RGB /F /Fl ID x EI")),
  ).toThrow("UNSUPPORTED_PDF");
  expect(() =>
    inspectInlineImages(bytes("BI /W 10 /H 10 /BPC 8 /CS /RGB ID x EI")),
  ).toThrow("UNSUPPORTED_PDF");
});

for (const options of [
  { level: 0 },
  { strategy: constants.Z_FIXED },
  { level: 6 },
]) {
  it(`uses compressed stream extent even when image data includes EI, ${JSON.stringify(options)}`, () => {
    const raster = Buffer.from(" EI ".repeat(10));
    const encoded = deflateSync(raster, options);
    const make = (data: Uint8Array) =>
      Buffer.concat([
        Buffer.from("BI /W 20 /H 2 /BPC 8 /CS /G /F /Fl ID "),
        data,
        Buffer.from(" EI Q"),
      ]);
    expect(() => inspectInlineImages(make(encoded))).not.toThrow();
    const broken = Buffer.from(encoded);
    broken[broken.length - 1] = broken[broken.length - 1]! ^ 1;
    expect(() => inspectInlineImages(make(broken))).toThrow();
    expect(() => inspectInlineImages(make(encoded.subarray(0, -4)))).toThrow();
    expect(() => inspectInlineImages(make(encoded), 20)).toThrow(
      "RESOURCE_LIMIT",
    );
  });
}
it("supports ASCII85 wrapped monochrome masks with exact decoded size", () => {
  const encoded = deflateSync(Buffer.alloc(12000, 85));
  let ascii = "";
  for (let at = 0; at < encoded.length; at += 4) {
    const part = encoded.subarray(at, at + 4);
    let n = 0;
    for (let j = 0; j < 4; j++) n = n * 256 + (part[j] ?? 0);
    const digits = Array(5).fill(0);
    for (let j = 4; j >= 0; j--) {
      digits[j] = 33 + (n % 85);
      n = Math.floor(n / 85);
    }
    ascii += String.fromCharCode(...digits.slice(0, part.length + 1));
  }
  const source = bytes(
    `BI /W 320 /H 300 /BPC 1 /IM true /F [/A85 /Fl] ID ${ascii}~> EI`,
  );
  expect(() => inspectInlineImages(source)).not.toThrow();
});
