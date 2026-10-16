import {
  PDFName,
  PDFNumber,
  degrees,
  PDFOperator,
  PDFOperatorNames,
  PDFArray,
  PDFDict,
} from "pdf-lib";
import { inspectPdf } from "../combine/generate";
import { inspectOverlay } from "../overlay/document";
import {
  displaySize,
  imageTransform,
  SIGN_LIMITS,
  type Geometry,
  type Placement,
} from "./model";
export async function inspectSign(bytes: Uint8Array) {
  return inspectOverlay(bytes, "signed");
}
export async function signPdf(
  bytes: Uint8Array,
  assets: { id: string; bytes: Uint8Array }[],
  placements: Placement[],
  stage: (s: string) => void = () => {},
) {
  stage("Checking your PDF…");
  const { doc, geometry } = await inspectSign(bytes);
  if (
    !placements.length ||
    placements.length > SIGN_LIMITS.instances ||
    !assets.length ||
    assets.length > SIGN_LIMITS.assets ||
    new Set(assets.map((a) => a.id)).size !== assets.length ||
    new Set(placements.map((p) => p.id)).size !== placements.length
  )
    throw Error("Invalid signature draft.");
  if (
    assets.reduce((n, a) => n + a.bytes.byteLength, 0) > SIGN_LIMITS.totalBytes
  )
    throw Error("Signature images exceed the task budget.");
  const images = new Map();
  for (const a of assets) {
    if (!placements.some((p) => p.asset === a.id)) continue;
    if (a.bytes.byteLength > SIGN_LIMITS.imageBytes)
      throw Error("Signature image is too large.");
    // Browser normalizes validated images to PNG; validate again at the worker boundary.
    if (
      a.bytes.length < 24 ||
      new DataView(a.bytes.buffer, a.bytes.byteOffset).getUint32(0) !==
        0x89504e47
    )
      throw Error("Invalid signature image.");
    const view = new DataView(a.bytes.buffer, a.bytes.byteOffset),
      w = view.getUint32(16),
      h = view.getUint32(20);
    if (!w || !h || w * h > SIGN_LIMITS.pixels)
      throw Error("Signature image exceeds the pixel budget.");
    images.set(a.id, await doc.embedPng(a.bytes));
  }
  stage("Adding your signatures…");
  for (const p of placements) {
    if (!Number.isInteger(p.page) || !geometry[p.page])
      throw Error("Choose an existing page.");
    const img = images.get(p.asset);
    if (!img) throw Error("Missing signature image.");
    const transform = imageTransform(p, geometry[p.page]!);
    if (Math.abs(p.width / p.height - img.width / img.height) > 0.01)
      throw Error("Keep signature proportions unchanged.");
    const page = doc.getPage(p.page);
    // Annotations (including widgets) paint above page content in PDF readers.
    // Refuse overlapping placements rather than export a signature hidden by them.
    const angle = (transform.angle * Math.PI) / 180;
    const corners = [
      [0, 0],
      [transform.width, 0],
      [0, transform.height],
      [transform.width, transform.height],
    ].map(([x, y]) => [
      transform.x + x! * Math.cos(angle) - y! * Math.sin(angle),
      transform.y + x! * Math.sin(angle) + y! * Math.cos(angle),
    ]);
    const left = Math.min(...corners.map((c) => c[0]!)),
      right = Math.max(...corners.map((c) => c[0]!)),
      bottom = Math.min(...corners.map((c) => c[1]!)),
      top = Math.max(...corners.map((c) => c[1]!));
    const annotations = page.node.Annots();
    for (let i = 0; i < (annotations?.size() ?? 0); i++) {
      const rect = annotations!
        .lookup(i, PDFDict)
        .lookupMaybe(PDFName.of("Rect"), PDFArray);
      if (!rect || rect.size() !== 4) continue;
      const xy = Array.from({ length: 4 }, (_, j) =>
        rect.lookup(j, PDFNumber).asNumber(),
      );
      if (
        left < Math.max(xy[0]!, xy[2]!) &&
        right > Math.min(xy[0]!, xy[2]!) &&
        bottom < Math.max(xy[1]!, xy[3]!) &&
        top > Math.min(xy[1]!, xy[3]!)
      )
        throw Error(
          `A signature on page ${p.page + 1} overlaps a form field or annotation. Move it to an unobstructed area. Your draft is unchanged.`,
        );
    }
    page.pushOperators(
      PDFOperator.of(PDFOperatorNames.BeginMarkedContent, [
        PDFName.of("Artifact"),
      ]),
    );
    page.drawImage(img, { ...transform, rotate: degrees(transform.angle) });
    page.pushOperators(PDFOperator.of(PDFOperatorNames.EndMarkedContent));
  }
  stage("Preparing your signed PDF…");
  const result = await doc.save();
  stage("Checking the signed PDF…");
  const verified = await inspectPdf(result, undefined, {
    preserveAnnotationExtensions: true,
  });
  if (!verified.ok || verified.pages !== geometry.length)
    throw Error(
      "The signed PDF did not pass validation. Your draft is unchanged.",
    );
  return result;
}
export type SignGeometry = Geometry;
export { displaySize };
