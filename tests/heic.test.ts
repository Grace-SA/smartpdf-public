import { expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { isHeic } from "../src/photos/heic-header";
import { inspectHeic as checkHeic } from "../src/photos/heic-inspect";
import { heicColor, toSrgb } from "../src/photos/heic-color";
const fixture = async () =>
  new Uint8Array(await readFile("tests/fixtures/photos/synthetic.heic"));
it("recognizes and bounds real HEIC metadata before decoding", async () => {
  const bytes = await fixture();
  expect(isHeic(bytes)).toBe(true);
  expect(() => checkHeic(bytes)).not.toThrow();
  expect(() => checkHeic(bytes.slice(0, 80))).toThrow();
  expect(isHeic(new Uint8Array([1, 2, 3]))).toBe(false);
  const hugeBrandBox = new Uint8Array(8192);
  hugeBrandBox.set(Buffer.from("ftypheic"), 4);
  new DataView(hugeBrandBox.buffer).setUint32(0, 8192);
  expect(isHeic(hugeBrandBox)).toBe(false);
});
it("refuses declared oversized pixels without decoding", async () => {
  const bytes = await fixture();
  const p = Buffer.from(bytes).indexOf("ispe");
  expect(p).toBeGreaterThan(0);
  new DataView(bytes.buffer).setUint32(p + 8, 100000);
  expect(() => checkHeic(bytes)).toThrow(/16 megapixels/);
});
it("converts a real sRGB ICC matrix/TRC profile without changing ordinary colors", async () => {
  const profile = await readFile("tests/fixtures/photos/synthetic-srgb.icc");
  const color = heicColor(Buffer.concat([Buffer.from("prof"), profile]));
  const before = new Uint8ClampedArray([
    255, 0, 0, 255, 20, 80, 180, 255, 128, 128, 128, 255,
  ]);
  const after = before.slice();
  toSrgb(after, color);
  expect(after.every((v, i) => Math.abs(v - before[i]!) <= 1)).toBe(true);
  expect(() => heicColor(new Uint8Array([1, 2, 3]))).toThrow(/color profile/);
});
it("rejects HDR and malformed color metadata before rendering", () => {
  const color = Buffer.alloc(11);
  color.write("nclx");
  color.writeUInt16BE(12, 4);
  color.writeUInt16BE(16, 6);
  expect(() => heicColor(color)).toThrow(/color profile/);
  const badIcc = Buffer.alloc(140);
  badIcc.write("prof");
  badIcc.write("RGB ", 20);
  badIcc.write("XYZ ", 24);
  badIcc.writeUInt32BE(99999, 132);
  expect(() => heicColor(badIcc)).toThrow(/color profile/);
});
it("maps Display-P3 midtones into sRGB and leaves alpha unchanged", () => {
  const color = Buffer.alloc(11);
  color.write("nclx");
  color.writeUInt16BE(12, 4);
  color.writeUInt16BE(13, 6);
  const pixels = new Uint8ClampedArray([128, 128, 128, 37, 180, 80, 60, 255]);
  toSrgb(pixels, heicColor(color));
  expect([...pixels.slice(0, 4)]).toEqual([128, 128, 128, 37]);
  expect(pixels[4]).toBeGreaterThan(180);
  expect(pixels[5]).toBeLessThan(80);
  expect(pixels[7]).toBe(255);
});
