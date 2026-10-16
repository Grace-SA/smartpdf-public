import { PDFDocument, degrees, PDFName } from "pdf-lib";
import { inspectPdf } from "../combine/generate";
import { validateSize } from "../core/contracts";
import { normalizeOptionalTagIndexes } from "../core/optional-tag-indexes";
import { compactStreamStorage } from "../organize/stream-storage";

export const rotateErrors = {
  invalid:
    "Choose one rotation for every page, in 90° steps, and change at least one page.",
  unsupported:
    "This PDF cannot be rotated while preserving its supported content and structure. Your original is unchanged.",
  output:
    "The rotated PDF did not pass validation. Your original and rotation draft are unchanged.",
} as const;

export async function rotatePdf(input: Uint8Array, turns: number[]) {
  validateSize(input.byteLength);
  const bytes = new Uint8Array(input);
  const check = await inspectPdf(bytes);
  if (!check.ok) throw new Error(rotateErrors.unsupported);
  if (
    turns.length !== check.pages ||
    !turns.some(Boolean) ||
    turns.some((turn) => !Number.isInteger(turn) || turn < 0 || turn > 3)
  )
    throw new Error(rotateErrors.invalid);
  const doc = await PDFDocument.load(bytes, {
    updateMetadata: false,
    throwOnInvalidObject: true,
  });
  const geometry = doc.getPages().map((page, index) => ({
    media: page.getMediaBox(),
    crop: page.getCropBox(),
    unit: page.node.get(PDFName.of("UserUnit"))?.toString(),
    rotation:
      (((page.getRotation().angle + turns[index]! * 90) % 360) + 360) % 360,
  }));
  normalizeOptionalTagIndexes(doc);
  // Keep the original page tree and objects: rotation is a viewer transform,
  // not page copying, content reconstruction or image conversion.
  doc
    .getPages()
    .forEach((page, index) =>
      page.setRotation(degrees(geometry[index]!.rotation)),
    );
  compactStreamStorage(doc);
  const result = await doc.save({ updateFieldAppearances: false });
  const verified = await inspectPdf(result);
  if (!verified.ok || verified.pages !== turns.length)
    throw new Error(rotateErrors.output);
  const output = await PDFDocument.load(result, {
    updateMetadata: false,
    throwOnInvalidObject: true,
  });
  for (const [index, page] of output.getPages().entries()) {
    const expected = geometry[index]!;
    if (
      JSON.stringify(page.getMediaBox()) !== JSON.stringify(expected.media) ||
      JSON.stringify(page.getCropBox()) !== JSON.stringify(expected.crop) ||
      page.node.get(PDFName.of("UserUnit"))?.toString() !== expected.unit ||
      page.getRotation().angle !== expected.rotation
    )
      throw new Error(rotateErrors.output);
  }
  return result;
}
