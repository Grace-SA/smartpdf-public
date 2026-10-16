/// <reference lib="webworker" />
import { PDFDocument, PDFDict, PDFName, PDFArray } from "pdf-lib";
const standard = new Set([
  "Times-Roman",
  "Times-Bold",
  "Times-Italic",
  "Times-BoldItalic",
  "Helvetica",
  "Helvetica-Bold",
  "Helvetica-Oblique",
  "Helvetica-BoldOblique",
  "Courier",
  "Courier-Bold",
  "Courier-Oblique",
  "Courier-BoldOblique",
  "Symbol",
  "ZapfDingbats",
]);
self.onmessage = async (event: MessageEvent<Uint8Array>) => {
  try {
    const doc = await PDFDocument.load(event.data, { updateMetadata: false });
    let warning = false;
    for (const [, object] of doc.context.enumerateIndirectObjects()) {
      if (
        !(object instanceof PDFDict) ||
        object.get(PDFName.of("Type"))?.toString() !== "/Font"
      )
        continue;
      const subtype = object.get(PDFName.of("Subtype"))?.toString();
      if (subtype?.startsWith("/CIDFont") || subtype === "/Type3") continue;
      const base =
        object.get(PDFName.of("BaseFont"))?.toString().slice(1) ?? "";
      if (standard.has(base)) continue;
      let owner = object;
      if (subtype === "/Type0") {
        const children = object.lookup(PDFName.of("DescendantFonts"));
        if (children instanceof PDFArray) {
          const child = children.lookup(0);
          if (child instanceof PDFDict) owner = child;
        }
      }
      const descriptor = owner.lookup(PDFName.of("FontDescriptor"));
      if (
        !(descriptor instanceof PDFDict) ||
        !["FontFile", "FontFile2", "FontFile3"].some((k) =>
          descriptor.has(PDFName.of(k)),
        )
      ) {
        warning = true;
        break;
      }
    }
    self.postMessage({ warning });
  } catch {
    self.postMessage({ warning: true });
  }
};
