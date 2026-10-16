import {
  PDFDocument,
  PDFPage,
  PDFObject,
  PDFDict,
  PDFArray,
  PDFRawStream,
  PDFRef,
  PDFName,
  decodePDFRawStream,
} from "pdf-lib";
import { inspectInlineImages } from "../core/inline-images";
import { LIMITS } from "../core/contracts";
import { StructureFailure } from "./structure";

// Prove that an orphan page index has no marked-content IDs to resolve. Names
// in strings/comments and bytes inside inline images do not count as MCIDs.
export function hasPageMcids(doc: PDFDocument, page: PDFPage): boolean {
  const seen = new Set<PDFObject>();
  let found = false;
  const resolve = (v: PDFObject | undefined) =>
    v instanceof PDFRef ? doc.context.lookup(v) : v;
  function walk(raw: PDFObject | undefined, content = false, depth = 0): void {
    const v = resolve(raw);
    if (!v || seen.has(v) || found) return;
    if (depth > LIMITS.depth || seen.size > LIMITS.nodes)
      throw new StructureFailure(
        "tagged",
        "Cannot verify this orphan page index within resource limits.",
      );
    seen.add(v);
    if (v instanceof PDFArray) {
      for (const x of v.asArray()) walk(x, content, depth + 1);
      return;
    }
    const d =
      v instanceof PDFRawStream ? v.dict : v instanceof PDFDict ? v : undefined;
    if (!d) return;
    if (d.has(PDFName.of("MCID"))) {
      found = true;
      return;
    }
    if (v instanceof PDFRawStream) {
      const subtype = d.get(PDFName.of("Subtype")),
        type = d.get(PDFName.of("Type"));
      if (
        content ||
        subtype === PDFName.of("Form") ||
        type === PDFName.of("Pattern")
      )
        inspectInlineImages(
          decodePDFRawStream(v).decode(),
          LIMITS.streamedImageWorkBytes,
          () => {
            found = true;
          },
        );
    }
    for (const [k, x] of d.entries())
      if (!["Parent", "P"].includes(k.decodeText())) walk(x, false, depth + 1);
  }
  walk(page.node.get(PDFName.of("Contents")), true);
  walk(page.node.Resources());
  return found;
}
