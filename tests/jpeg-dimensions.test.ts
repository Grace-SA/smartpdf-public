import { test, expect } from "vitest";
import { checkJpegDimensions } from "../src/core/jpeg-dimensions";
import { jpegResourceFixture } from "./jpeg-resource-fixture";
import { probePdf } from "../src/core/probe";
import { combinePdfs } from "../src/combine/generate";
import { PDFDocument } from "pdf-lib";
import { writeFile } from "node:fs/promises";

// Marker-only cases test the bounded header scanner, not pixel decoding.
function markers(width = 6000, height = 4000, sof = 0xc0) {
  return Uint8Array.from([
    255,
    216,
    255,
    sof,
    0,
    11,
    8,
    height >> 8,
    height & 255,
    width >> 8,
    width & 255,
    1,
    1,
    17,
    0,
    255,
    218,
    0,
    8,
    1,
    1,
    0,
    0,
    63,
    0,
    42,
    255,
    0,
    255,
    208,
    255,
    217,
  ]);
}
test("24 MP boundary accepts baseline and progressive headers; larger frames fail", () => {
  for (const sof of [0xc0, 0xc1, 0xc2])
    expect(() =>
      checkJpegDimensions(markers(6000, 4000, sof), 6000, 4000),
    ).not.toThrow();
  expect(() => checkJpegDimensions(markers(6000, 4001), 1, 1)).toThrowError(
    expect.objectContaining({ reason: "image" }),
  );
});
test("mismatched declarations, absent frame, truncation and zero dimensions fail closed", () => {
  for (const data of [
    markers(0, 4000),
    markers().slice(0, -2),
    Uint8Array.of(255, 216, 255, 217),
    markers(),
  ])
    expect(() => checkJpegDimensions(data, 1, 1)).toThrow();
});
test("later frame and DNL cannot override already checked dimensions", () => {
  for (const marker of [0xc0, 0xc2, 0xdc]) {
    const data = Uint8Array.from([
      ...markers().slice(0, -2),
      255,
      marker,
      0,
      4,
      0,
      1,
      255,
      217,
    ]);
    expect(() => checkJpegDimensions(data, 6000, 4000)).toThrow();
  }
});
for (const wrapped of [false, true])
  for (const understated of [false, true])
    test(`real 30 MP JPEG is rejected before preview and merge: wrapped=${wrapped}, understated=${understated}`, async () => {
      const bytes = await jpegResourceFixture(wrapped, understated);
      if (wrapped && understated)
        await writeFile(
          "tests/fixtures/combine/final-jpeg-overlimit.pdf",
          bytes,
        );
      for (const mode of ["preview", "combine"] as const)
        expect(await probePdf(bytes, mode)).toMatchObject({
          ok: false,
          reason: "image",
          code: "RESOURCE_LIMIT",
        });
      const blank = await PDFDocument.create();
      blank.addPage();
      await expect(
        combinePdfs([bytes, await blank.save()], () => {}),
      ).rejects.toThrow();
    });
