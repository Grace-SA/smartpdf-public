import { deflateSync } from "node:zlib";
import { PDFDict, PDFDocument, PDFName, PDFRawStream, PDFRef } from "pdf-lib";
import { describe, expect, it, vi } from "vitest";
import {
  recompressCommonImages,
  undoPngPredictor,
  type RgbJpegEncoder,
} from "../src/compress/images";

const k = PDFName.of;

describe("common image compression", () => {
  it("undoes all PNG row filters", () => {
    const expected = new Uint8Array([
      10, 20, 30, 40, 50, 60, 15, 25, 35, 45, 55, 65, 20, 30, 40, 50, 60, 70,
      25, 35, 45, 55, 65, 75, 30, 40, 50, 60, 70, 80,
    ]);
    const filtered = new Uint8Array([
      0, 10, 20, 30, 40, 50, 60, 1, 15, 25, 35, 30, 30, 30, 2, 5, 5, 5, 5, 5, 5,
      3, 15, 20, 25, 18, 18, 18, 4, 5, 5, 5, 5, 5, 5,
    ]);
    expect([...undoPngPredictor(filtered, 2, 5)]).toEqual([...expected]);
  });

  it("replaces eligible RGB images while retaining the soft mask reference", async () => {
    const doc = await PDFDocument.create();
    const width = 300;
    const height = 300;
    const rgb = new Uint8Array(width * height * 3);
    let random = 0x12345678;
    for (let index = 0; index < rgb.length; index += 1) {
      random ^= random << 13;
      random ^= random >>> 17;
      random ^= random << 5;
      rgb[index] = random & 0xff;
    }
    const predicted = new Uint8Array((width * 3 + 1) * height);
    for (let row = 0; row < height; row += 1) {
      predicted[row * (width * 3 + 1)] = 0;
      predicted.set(
        rgb.subarray(row * width * 3, (row + 1) * width * 3),
        row * (width * 3 + 1) + 1,
      );
    }
    const mask = doc.context.register(
      PDFRawStream.of(
        doc.context.obj({
          Type: "XObject",
          Subtype: "Image",
          Width: width,
          Height: height,
          ColorSpace: "DeviceGray",
          BitsPerComponent: 8,
          Filter: "FlateDecode",
        }) as PDFDict,
        deflateSync(new Uint8Array(width * height).fill(255)),
      ),
    );
    const image = doc.context.register(
      PDFRawStream.of(
        doc.context.obj({
          Type: "XObject",
          Subtype: "Image",
          Width: width,
          Height: height,
          ColorSpace: "DeviceRGB",
          BitsPerComponent: 8,
          Filter: "FlateDecode",
          DecodeParms: {
            Predictor: 15,
            Colors: 3,
            BitsPerComponent: 8,
            Columns: width,
          },
          SMask: mask,
        }) as PDFDict,
        deflateSync(predicted),
      ),
    );
    const page = doc.addPage([300, 300]);
    const resources = doc.context.obj({ XObject: { Im1: image } });
    page.node.set(k("Resources"), resources);
    const source = await doc.save({ useObjectStreams: false });
    const jpeg = new Uint8Array(2_000).fill(42);
    const encoder = vi.fn<RgbJpegEncoder>(async () => jpeg);

    const result = await recompressCommonImages(source, "recommended", encoder);

    expect(result.replacedImages).toBe(1);
    expect(encoder).toHaveBeenCalledOnce();
    expect(encoder.mock.calls[0]![0]).toEqual(rgb);
    expect(encoder.mock.calls[0]!.slice(1)).toEqual([width, height, 0.8]);
    const output = await PDFDocument.load(result.bytes);
    const converted = output.context.lookup(image) as PDFRawStream;
    expect(converted.dict.get(k("Filter"))).toBe(k("DCTDecode"));
    expect(converted.dict.has(k("DecodeParms"))).toBe(false);
    expect(converted.dict.get(k("SMask"))).toBeInstanceOf(PDFRef);
    expect((converted.dict.get(k("SMask")) as PDFRef).toString()).toBe(
      mask.toString(),
    );
    const unchangedMask = output.context.lookup(mask) as PDFRawStream;
    expect(unchangedMask.dict.get(k("ColorSpace"))).toBe(k("DeviceGray"));
  });

  it("does not touch unsupported color spaces or highest-quality mode", async () => {
    const source = new Uint8Array(await (await PDFDocument.create()).save());
    const encoder = vi.fn(async () => new Uint8Array(10));
    const result = await recompressCommonImages(source, "quality", encoder);
    expect(result.bytes).toBe(source);
    expect(result.replacedImages).toBe(0);
    expect(encoder).not.toHaveBeenCalled();
  });
});
