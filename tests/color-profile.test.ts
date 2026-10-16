import { it, expect } from "vitest";
import { deflateSync } from "node:zlib";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import {
  PDFDocument,
  PDFName,
  PDFRawStream,
  PDFArray,
  decodePDFRawStream,
} from "pdf-lib";
import { inspectImageColor } from "../src/photos/color-profile";
import { generatePhotos } from "../src/photos/generate";
import { defaultSettings } from "../src/photos/model";
import { combinePdfs } from "../src/combine/generate";
import { organizePdf } from "../src/organize/generate";
const fixture = async (name: string) =>
  new Uint8Array(await readFile(`tests/fixtures/photos/${name}`));
it("preserves new photo color spaces through merge and page reordering", async () => {
  const input = await generatePhotos(
    await Promise.all(
      ["color-linear.jpg", "color-linear.png", "color-gamma.png"].map(
        async (name) => ({ bytes: await fixture(name), turns: 0 }),
      ),
    ),
    defaultSettings,
    () => {},
  );
  const blank = await PDFDocument.create();
  blank.addPage();
  const merged = await combinePdfs([input, await blank.save()], () => {});
  const reordered = await organizePdf(
    merged,
    [2, 1, 0, 3].map((source) => ({ id: String(source), source, turns: 1 })),
  );
  const final = await PDFDocument.load(reordered);
  expect(final.getPageCount()).toBe(4);
  const spaces = final.context
    .enumerateIndirectObjects()
    .flatMap(([, object]) =>
      object instanceof PDFRawStream &&
      object.dict.get(PDFName.of("Subtype")) === PDFName.of("Image") &&
      object.dict.get(PDFName.of("ColorSpace")) instanceof PDFArray
        ? [
            (object.dict.get(PDFName.of("ColorSpace")) as PDFArray)
              .get(0)
              ?.toString(),
          ]
        : [],
    );
  expect(spaces.sort()).toEqual(["/CalRGB", "/ICCBased", "/ICCBased"]);
});
it("retains JPEG ICC and compressed pixels, PNG ICC and alpha, and calibrated gamma", async () => {
  const names = ["color-linear.jpg", "color-linear.png", "color-gamma.png"];
  const inputs = await Promise.all(
    names.map(async (name) => ({ bytes: await fixture(name), turns: 0 })),
  );
  const output = await generatePhotos(inputs, defaultSettings, () => {});
  const doc = await PDFDocument.load(output);
  const images = doc.context
    .enumerateIndirectObjects()
    .map(([, o]) => o)
    .filter(
      (o): o is PDFRawStream =>
        o instanceof PDFRawStream &&
        o.dict.get(PDFName.of("Subtype")) === PDFName.of("Image") &&
        o.dict.get(PDFName.of("ColorSpace")) instanceof PDFArray,
    );
  expect(images).toHaveLength(3);
  for (const image of images.slice(0, 2)) {
    const space = image.dict.lookup(PDFName.of("ColorSpace"), PDFArray);
    expect(space.get(0)).toBe(PDFName.of("ICCBased"));
    const profile = doc.context.lookup(space.get(1)) as PDFRawStream;
    const color = await inspectImageColor(inputs[0]!.bytes, "jpeg");
    expect(Buffer.from(decodePDFRawStream(profile).decode())).toEqual(
      Buffer.from((color as { icc: Uint8Array }).icc),
    );
  }
  expect(Buffer.from(images[0]!.contents)).toEqual(
    Buffer.from(inputs[0]!.bytes),
  );
  expect(images[1]!.dict.has(PDFName.of("SMask"))).toBe(true);
  expect(
    images[2]!.dict.lookup(PDFName.of("ColorSpace"), PDFArray).get(0),
  ).toBe(PDFName.of("CalRGB"));
  await mkdir("docs/private-samples/m1", { recursive: true });
  await writeFile("docs/private-samples/m1/color-managed.pdf", output);
});
it("rejects incomplete or mismatched JPEG ICC instead of silently stripping it", async () => {
  const bytes = await fixture("color-linear.jpg");
  const at = Buffer.from(bytes).indexOf("ICC_PROFILE\0");
  const broken = bytes.slice();
  broken[at + 13] = 2;
  await expect(inspectImageColor(broken, "jpeg")).rejects.toThrow(
    "color settings",
  );
  const wrong = bytes.slice();
  wrong.set(new TextEncoder().encode("CMYK"), at + 14 + 16);
  await expect(inspectImageColor(wrong, "jpeg")).rejects.toThrow(
    "color settings",
  );
});
it("bounds PNG profile inflation and rejects ambiguous or HDR color settings", async () => {
  const original = await fixture("synthetic-control.png");
  const chunk = (kind: string, data: Buffer) => {
    const size = Buffer.alloc(4);
    size.writeUInt32BE(data.length);
    return Buffer.concat([size, Buffer.from(kind), data, Buffer.alloc(4)]);
  };
  const withChunks = (...chunks: Buffer[]) =>
    Buffer.concat([original.subarray(0, 33), ...chunks, original.subarray(33)]);
  const bomb = chunk(
    "iCCP",
    Buffer.concat([
      Buffer.from([80, 0, 0]),
      deflateSync(Buffer.alloc(1024 * 1024 + 1)),
    ]),
  );
  await expect(inspectImageColor(withChunks(bomb), "png")).rejects.toThrow(
    "color settings",
  );
  await expect(
    inspectImageColor(
      withChunks(chunk("cICP", Buffer.from([9, 16, 0, 1]))),
      "png",
    ),
  ).rejects.toThrow("color settings");
  const gamma = Buffer.alloc(4);
  gamma.writeUInt32BE(100000);
  await expect(
    inspectImageColor(
      withChunks(chunk("gAMA", gamma), chunk("gAMA", gamma)),
      "png",
    ),
  ).rejects.toThrow("color settings");
});
it("assembles split JPEG ICC chunks by index and rejects duplicate chunks", async () => {
  const bytes = await fixture("color-linear.jpg");
  const expected = await inspectImageColor(bytes, "jpeg");
  const at = Buffer.from(bytes).indexOf("ICC_PROFILE\0");
  const marker = at - 4,
    length = new DataView(bytes.buffer, bytes.byteOffset).getUint16(at - 2);
  const profile = (expected as { icc: Uint8Array }).icc;
  const part = (index: number, data: Uint8Array) => {
    const header = Buffer.alloc(4);
    header[0] = 255;
    header[1] = 226;
    header.writeUInt16BE(data.length + 16, 2);
    return Buffer.concat([
      header,
      Buffer.from("ICC_PROFILE\0"),
      Buffer.from([index, 2]),
      data,
    ]);
  };
  const first = part(1, profile.subarray(0, 100)),
    second = part(2, profile.subarray(100));
  const split = Buffer.concat([
    bytes.subarray(0, marker),
    second,
    first,
    bytes.subarray(marker + length + 2),
  ]);
  expect(await inspectImageColor(split, "jpeg")).toEqual(expected);
  const duplicate = Buffer.concat([
    bytes.subarray(0, marker),
    first,
    first,
    bytes.subarray(marker + length + 2),
  ]);
  await expect(inspectImageColor(duplicate, "jpeg")).rejects.toThrow(
    "color settings",
  );
});
