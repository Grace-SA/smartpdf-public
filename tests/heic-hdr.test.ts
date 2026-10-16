import { expect, it } from "vitest";
import { inspectHeic } from "../src/photos/heic-inspect";
const u16 = (n: number) => {
  const b = Buffer.alloc(2);
  b.writeUInt16BE(n);
  return b;
};
const u32 = (n: number) => {
  const b = Buffer.alloc(4);
  b.writeUInt32BE(n);
  return b;
};
const box = (kind: string, ...data: Uint8Array[]) => {
  const b = Buffer.concat(data);
  return Buffer.concat([u32(b.length + 8), Buffer.from(kind), b]);
};
const full = Buffer.alloc(4);
function sample(hdrPrimary = false, target = 1) {
  const color = (transfer: number) =>
    box(
      "colr",
      Buffer.from("nclx"),
      u16(1),
      u16(transfer),
      u16(1),
      Buffer.from([128]),
    );
  const props = box(
    "ipco",
    color(hdrPrimary ? 16 : 13),
    box("ispe", full, u32(320), u32(240)),
    box("auxC", full, Buffer.from("urn:com:apple:photo:2020:aux:hdrgainmap\0")),
    color(16),
  );
  const assoc = box(
    "ipma",
    full,
    u32(2),
    u16(1),
    Buffer.from([2, 1, 2]),
    u16(2),
    Buffer.from([2, 3, 4]),
  );
  const ref = box("iref", full, box("auxl", u16(2), u16(1), u16(target)));
  return Buffer.concat([
    box("ftyp", Buffer.from("heic"), u32(0), Buffer.from("mif1")),
    box(
      "meta",
      full,
      box("pitm", full, u16(1)),
      box("iprp", props, assoc),
      ref,
    ),
    u32(1),
    Buffer.from("mdat"),
    u32(0),
    u32(16),
  ]);
}
it("accepts an SDR primary with Apple gain map and a legal extended-length data box", () => {
  const result = inspectHeic(sample());
  expect(result.hdrGainMap).toBe(true);
  expect(result.color).toBeUndefined();
});
it("does not use auxiliary HDR color metadata as the primary photo profile", () => {
  expect(() => inspectHeic(sample(false))).not.toThrow();
  expect(() => inspectHeic(sample(true))).toThrow(/HDR-only primary/);
});
it("rejects an unverified gain-map association and oversized 64-bit box length", () => {
  expect(() => inspectHeic(sample(false, 3))).toThrow(/HDR structure/);
  const data = sample();
  data.writeUInt32BE(0xffffffff, data.length - 8);
  expect(() => inspectHeic(data)).toThrow(/structure/);
});
