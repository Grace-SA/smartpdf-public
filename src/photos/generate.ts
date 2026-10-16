import {
  PDFDocument,
  pushGraphicsState,
  popGraphicsState,
  concatTransformationMatrix,
  drawObject,
} from "pdf-lib";
import { inspectImageColor, preserveImageColor } from "./color-profile";
import {
  inspectImage,
  layout,
  PHOTO_LIMITS,
  photoCopy,
  type PhotoSettings,
} from "./model";
export type PhotoInput = { bytes: Uint8Array; turns: number };
export async function generatePhotos(
  inputs: PhotoInput[],
  settings: PhotoSettings,
  progress: (done: number) => void,
) {
  if (
    !inputs.length ||
    inputs.length > PHOTO_LIMITS.count ||
    inputs.reduce((n, x) => n + x.bytes.length, 0) > PHOTO_LIMITS.inputBytes
  )
    throw new Error(photoCopy.total);
  const doc = await PDFDocument.create();
  for (const [index, input] of inputs.entries()) {
    const info = inspectImage(input.bytes);
    const color = await inspectImageColor(input.bytes, info.format);
    const image =
      info.format === "jpeg"
        ? await doc.embedJpg(input.bytes)
        : await doc.embedPng(input.bytes);
    await preserveImageColor(doc, image, color);
    if (image.width !== info.width || image.height !== info.height)
      throw new Error(photoCopy.invalid);
    const box = layout(info, input.turns, settings),
      page = doc.addPage([box.width, box.height]);
    const key = page.node.newXObject("Photo", image.ref);
    page.pushOperators(
      pushGraphicsState(),
      concatTransformationMatrix(...box.matrix),
      drawObject(key),
      popGraphicsState(),
    );
    progress(index + 1);
  }
  return doc.save();
}
