import {
  PDFArray,
  PDFDict,
  PDFName,
  PDFNumber,
  PDFOperator,
  PDFOperatorNames,
  concatTransformationMatrix,
  pushGraphicsState,
  popGraphicsState,
  rgb,
} from "pdf-lib";
import fontkit from "@pdf-lib/fontkit";
import { inspectOverlay } from "../overlay/document";
import {
  pdfPoint,
  stampMatrix,
  type Geometry,
  type Rect,
} from "../overlay/geometry";
import { inspectPdf } from "../combine/generate";
import { compactStreamStorage } from "../organize/stream-storage";
import { LIMITS } from "../core/contracts";
import {
  WATERMARK_LIMITS,
  planWatermarks,
  type WatermarkSettings,
} from "./model";
import { textShape } from "./font";
import { inspectImage } from "../photos/model";
export type WatermarkImage = {
  bytes: Uint8Array;
  width: number;
  height: number;
};
export async function inspectWatermark(bytes: Uint8Array) {
  const { doc, geometry } = await inspectOverlay(bytes, "watermarked");
  const annotations = doc.getPages().map((page, index) => {
    const rects: Rect[] = [],
      list = page.node.Annots();
    for (let i = 0; i < (list?.size() ?? 0); i++) {
      const annot = list!.lookup(i, PDFDict),
        flags = annot.lookupMaybe(PDFName.of("F"), PDFNumber)?.asNumber() ?? 0;
      if (flags & (1 | 2 | 32)) continue;
      if (
        annot.lookupMaybe(PDFName.of("Subtype"), PDFName)?.toString() ===
          "/Link" &&
        !annot.has(PDFName.of("AP"))
      )
        continue;
      const rect = annot.lookupMaybe(PDFName.of("Rect"), PDFArray);
      if (!rect || rect.size() !== 4) continue;
      const p = Array.from({ length: 4 }, (_, j) =>
        rect.lookup(j, PDFNumber).asNumber(),
      );
      const points = [
        [p[0]!, p[1]!],
        [p[0]!, p[3]!],
        [p[2]!, p[1]!],
        [p[2]!, p[3]!],
      ].map(([x, y]) => pdfPoint(geometry[index]!, x!, y!));
      const x = Math.min(...points.map((p) => p[0])),
        y = Math.min(...points.map((p) => p[1]));
      rects.push({
        x,
        y,
        width: Math.max(...points.map((p) => p[0])) - x,
        height: Math.max(...points.map((p) => p[1])) - y,
      });
    }
    return rects;
  });
  return { doc, geometry, annotations };
}
export type WatermarkInspection = {
  geometry: Geometry[];
  annotations: Rect[][];
};
export async function watermarkPdf(
  input: Uint8Array,
  settings: WatermarkSettings,
  fontBytes: Uint8Array,
  image?: WatermarkImage,
  stage: (value: string) => void = () => {},
) {
  stage("Checking your PDF…");
  const { doc, geometry, annotations } = await inspectWatermark(input);
  const original = doc.getPages().map((p) => ({
    media: p.getMediaBox(),
    crop: p.getCropBox(),
    rotation: p.getRotation().angle,
    unit: p.node.get(PDFName.of("UserUnit"))?.toString(),
  }));
  if (fontBytes.byteLength > WATERMARK_LIMITS.fontBytes)
    throw Error("The watermark font exceeds its budget.");
  const shape =
    settings.type === "text" ? textShape(fontBytes, settings.text) : null;
  if (
    settings.type === "image" &&
    (!image ||
      image.bytes.length > WATERMARK_LIMITS.imageBytes ||
      image.width * image.height > WATERMARK_LIMITS.pixels ||
      image.width < 1 ||
      image.height < 1)
  )
    throw Error("Choose a PNG or JPEG watermark up to 5 MiB and 4 MP.");
  if (settings.type === "image") {
    const actual = inspectImage(image!.bytes);
    if (
      actual.format !== "png" ||
      actual.width !== image!.width ||
      actual.height !== image!.height ||
      actual.width * actual.height > WATERMARK_LIMITS.pixels
    )
      throw Error("Invalid watermark image dimensions.");
  }
  const plan = planWatermarks(
    settings,
    geometry,
    shape ? shape.width / shape.height : image!.width / image!.height,
    annotations,
  );
  doc.registerFontkit(fontkit);
  const font = shape ? await doc.embedFont(fontBytes, { subset: true }) : null;
  const img =
    image && settings.type === "image" ? await doc.embedPng(image.bytes) : null;
  if (img && (img.width !== image!.width || img.height !== image!.height))
    throw Error("The watermark image dimensions changed.");
  const color = rgb(
    parseInt(settings.color.slice(1, 3), 16) / 255,
    parseInt(settings.color.slice(3, 5), 16) / 255,
    parseInt(settings.color.slice(5, 7), 16) / 255,
  );
  for (const [n, index] of plan.pages.entries()) {
    stage(`Adding watermarks to page ${n + 1} of ${plan.pages.length}…`);
    const page = doc.getPage(index);
    for (const stamp of plan.stamps[index]!) {
      page.pushOperators(
        pushGraphicsState(),
        PDFOperator.of(PDFOperatorNames.BeginMarkedContent, [
          PDFName.of("Artifact"),
        ]),
        concatTransformationMatrix(
          ...stampMatrix(
            geometry[index]!,
            stamp.cx,
            stamp.cy,
            stamp.width,
            stamp.height,
            stamp.angle,
          ),
        ),
      );
      if (shape && font) {
        const scale = stamp.width / shape.width;
        page.drawText(shape.text, {
          font,
          size: shape.units * scale,
          x: -shape.left * scale,
          y: -shape.bottom * scale,
          color,
          opacity: settings.opacity / 100,
        });
      } else if (img)
        page.drawImage(img, {
          x: 0,
          y: 0,
          width: stamp.width,
          height: stamp.height,
          opacity: settings.opacity / 100,
        });
      page.pushOperators(
        PDFOperator.of(PDFOperatorNames.EndMarkedContent),
        popGraphicsState(),
      );
    }
  }
  compactStreamStorage(doc);
  const output = await doc.save({ updateFieldAppearances: false });
  if (
    output.length > LIMITS.bytes ||
    input.length + output.length + (image?.bytes.length ?? 0) > 60 * 1024 * 1024
  )
    throw Error(
      "This watermarked PDF exceeds the task budget. Use a smaller image or fewer pages. Your original is unchanged.",
    );
  stage("Checking the watermarked PDF…");
  const check = await inspectPdf(output, undefined, {
    preserveAnnotationExtensions: true,
  });
  if (!check.ok || check.pages !== geometry.length)
    throw Error(
      "The watermarked PDF did not pass validation. Your original is unchanged.",
    );
  const verified = await inspectOverlay(output, "watermarked");
  verified.doc.getPages().forEach((page, i) => {
    const g = original[i]!;
    if (
      JSON.stringify(page.getMediaBox()) !== JSON.stringify(g.media) ||
      JSON.stringify(page.getCropBox()) !== JSON.stringify(g.crop) ||
      page.getRotation().angle !== g.rotation ||
      page.node.get(PDFName.of("UserUnit"))?.toString() !== g.unit
    )
      throw Error("Page geometry changed during watermarking.");
  });
  return output;
}
