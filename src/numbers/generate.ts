import {
  PDFName,
  PDFOperator,
  PDFOperatorNames,
  pushGraphicsState,
  popGraphicsState,
  concatTransformationMatrix,
  rgb,
} from "pdf-lib";
import fontkit from "@pdf-lib/fontkit";
import { inspectOverlay } from "../overlay/document";
import { stampMatrix, type Geometry, type Rect } from "../overlay/geometry";
import { glyphShape } from "../overlay/text";
import { inspectPdf } from "../combine/generate";
import { compactStreamStorage } from "../organize/stream-storage";
import { LIMITS } from "../core/contracts";
import { planNumbers, type NumberSettings } from "./model";

export type NumberInspection = { geometry: Geometry[]; annotations: Rect[][] };
export function inspectNumbers(bytes: Uint8Array) {
  return inspectOverlay(bytes, "numbered");
}
export async function numberPdf(
  input: Uint8Array,
  settings: NumberSettings,
  fontBytes: Uint8Array,
  stage: (text: string) => void = () => {},
) {
  stage("Checking your PDF…");
  const { doc, geometry, annotations } = await inspectNumbers(input);
  if (!fontBytes.byteLength || fontBytes.byteLength > 64 * 1024)
    throw Error("The page number font exceeds its budget.");
  const plan = planNumbers(
    settings,
    geometry,
    (text) => glyphShape(fontBytes, text),
    annotations,
  );
  const snapshot = doc.getPages().map((p) => ({
    media: p.getMediaBox(),
    crop: p.getCropBox(),
    rotation: p.getRotation().angle,
    unit: p.node.get(PDFName.of("UserUnit"))?.toString(),
  }));
  const labels = doc.catalog.get(PDFName.of("PageLabels"))?.toString();
  doc.registerFontkit(fontkit);
  const font = await doc.embedFont(fontBytes, { subset: true });
  const color = rgb(
    parseInt(settings.color.slice(1, 3), 16) / 255,
    parseInt(settings.color.slice(3, 5), 16) / 255,
    parseInt(settings.color.slice(5, 7), 16) / 255,
  );
  for (const [ordinal, index] of plan.pages.entries()) {
    stage(`Adding numbers to page ${ordinal + 1} of ${plan.pages.length}…`);
    const page = doc.getPage(index),
      stamp = plan.stamps[index]!,
      scale = settings.size / stamp.shape.units;
    page.pushOperators(
      pushGraphicsState(),
      PDFOperator.of(PDFOperatorNames.BeginMarkedContent, [
        PDFName.of("Artifact"),
      ]),
      concatTransformationMatrix(
        ...stampMatrix(
          geometry[index]!,
          stamp.x + stamp.width / 2,
          stamp.y + stamp.height / 2,
          stamp.width,
          stamp.height,
          0,
        ),
      ),
    );
    page.drawText(stamp.text, {
      font,
      size: settings.size,
      x: -stamp.shape.left * scale,
      y: -stamp.shape.bottom * scale,
      color,
    });
    page.pushOperators(
      PDFOperator.of(PDFOperatorNames.EndMarkedContent),
      popGraphicsState(),
    );
  }
  compactStreamStorage(doc);
  const output = await doc.save({ updateFieldAppearances: false });
  if (
    output.length > LIMITS.bytes ||
    input.length + output.length > 60 * 1024 * 1024
  )
    throw Error(
      "The numbered PDF exceeds the task budget. Your original is unchanged.",
    );
  stage("Checking your numbered PDF…");
  const check = await inspectPdf(output, undefined, {
    preserveAnnotationExtensions: true,
  });
  if (!check.ok || check.pages !== geometry.length)
    throw Error(
      "The numbered PDF did not pass validation. Your original is unchanged.",
    );
  const verified = await inspectNumbers(output);
  if (verified.doc.catalog.get(PDFName.of("PageLabels"))?.toString() !== labels)
    throw Error("The PDF page labels changed during numbering.");
  verified.doc.getPages().forEach((page, index) => {
    const g = snapshot[index]!;
    if (
      JSON.stringify(page.getMediaBox()) !== JSON.stringify(g.media) ||
      JSON.stringify(page.getCropBox()) !== JSON.stringify(g.crop) ||
      page.getRotation().angle !== g.rotation ||
      page.node.get(PDFName.of("UserUnit"))?.toString() !== g.unit
    )
      throw Error("Page geometry changed during numbering.");
  });
  return output;
}
