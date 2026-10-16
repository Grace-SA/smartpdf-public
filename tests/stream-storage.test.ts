import { test, expect } from "vitest";
import {
  PDFDocument,
  PDFName,
  PDFRawStream,
  decodePDFRawStream,
} from "pdf-lib";
import { compactStreamStorage } from "../src/organize/stream-storage";
import { deflateSync } from "node:zlib";
function ascii85(bytes: Uint8Array) {
  let text = "";
  for (let i = 0; i < bytes.length; i += 4) {
    const n = Math.min(4, bytes.length - i);
    let v = 0;
    for (let j = 0; j < 4; j++) v = v * 256 + (bytes[i + j] ?? 0);
    const digits = [];
    for (let j = 0; j < 5; j++) {
      digits.unshift((v % 85) + 33);
      v = Math.floor(v / 85);
    }
    text += String.fromCharCode(...digits.slice(0, n + 1));
  }
  return new TextEncoder().encode(text + "~>");
}
test("storage compaction keeps exact compressed payload, decoder result and source stream", async () => {
  const d = await PDFDocument.create(),
    original = new TextEncoder().encode("q 1 0 0 1 0 0 cm Q ".repeat(200));
  const compressed = deflateSync(original),
    encoded = ascii85(compressed);
  const stream = PDFRawStream.of(
      d.context.obj({ Filter: ["ASCII85Decode", "FlateDecode"] }),
      encoded,
    ),
    ref = d.context.register(stream);
  compactStreamStorage(d);
  const out = d.context.lookup(ref) as PDFRawStream;
  expect([...out.contents]).toEqual([...compressed]);
  expect([...decodePDFRawStream(out).decode()]).toEqual([...original]);
  expect(out.dict.get(PDFName.of("Filter"))).toBe(PDFName.of("FlateDecode"));
  expect(stream.contents).toBe(encoded);
});
test("streams with decode parameters are preserved unchanged", async () => {
  const d = await PDFDocument.create(),
    s = PDFRawStream.of(
      d.context.obj({
        Filter: ["ASCII85Decode", "FlateDecode"],
        DecodeParms: [null, { Predictor: 12 }],
      }),
      new Uint8Array([1, 2, 3]),
    ),
    ref = d.context.register(s);
  compactStreamStorage(d);
  expect(d.context.lookup(ref)).toBe(s);
});
