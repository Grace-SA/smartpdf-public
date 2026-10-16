import { PDFDocument } from "pdf-lib";
import { inspectPdf } from "../combine/generate";
import { validateSize } from "../core/contracts";
import { normalizeOptionalTagIndexes } from "../core/optional-tag-indexes";
import { reasons } from "../copy";
import { pageGeometry } from "./geometry";
export async function inspectOverlay(bytes: Uint8Array, operation: string) {
  validateSize(bytes.byteLength);
  const check = await inspectPdf(bytes, undefined, {
    preserveAnnotationExtensions: true,
  });
  if (!check.ok)
    throw Error(
      `This PDF cannot be ${operation} safely. ` +
        (check.detail ||
          (check.reason && reasons[check.reason]) ||
          "Unsupported document structure.") +
        " Your original is unchanged.",
    );
  const doc = await PDFDocument.load(bytes, {
    updateMetadata: false,
    throwOnInvalidObject: true,
  });
  normalizeOptionalTagIndexes(doc);
  return { doc, geometry: doc.getPages().map(pageGeometry) };
}
