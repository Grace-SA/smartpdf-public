import { PDFDocument, PDFArray, PDFDict, PDFName, PDFNumber } from "pdf-lib";
import { inspectPdf } from "../combine/generate";
import { validateSize } from "../core/contracts";
import { normalizeOptionalTagIndexes } from "../core/optional-tag-indexes";
import { reasons } from "../copy";
import { pageGeometry, pdfPoint, type Rect } from "./geometry";
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
  const geometry = doc.getPages().map(pageGeometry);
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
