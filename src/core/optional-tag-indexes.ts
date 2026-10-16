import { PDFDocument, PDFDict, PDFName, PDFRef, PDFNull } from "pdf-lib";

// ISO 32000 treats an undefined indirect object as null. Restrict this
// normalization to optional tag indexes and absent annotation appearances; required content/resource references
// must still fail. inspectTags separately requires indexes when items use them.
export function normalizeOptionalTagIndexes(doc: PDFDocument): void {
  // Object zero is reserved and denotes null. Apple exports sometimes use
  // 0 0 R for an absent normal annotation appearance (also in their mirror).
  const visited = new Set<PDFDict>();
  const pending = doc.context
    .enumerateIndirectObjects()
    .map(([, object]) => object)
    .filter((object): object is PDFDict => object instanceof PDFDict);
  while (pending.length) {
    const d = pending.pop()!;
    if (visited.has(d)) continue;
    visited.add(d);
    for (const [name, raw] of d.entries()) {
      const value = doc.context.lookup(raw);
      if (!(value instanceof PDFDict)) continue;
      if (name === PDFName.of("AP")) {
        const normal = value.get(PDFName.of("N"));
        if (
          normal instanceof PDFRef &&
          normal.objectNumber === 0 &&
          normal.generationNumber === 0 &&
          !doc.context.lookup(normal)
        )
          value.set(PDFName.of("N"), PDFNull);
      }
      pending.push(value);
    }
  }
  const root = doc.context.lookup(
    doc.catalog.get(PDFName.of("StructTreeRoot")),
  );
  if (!(root instanceof PDFDict)) return;
  for (const name of ["ParentTree", "IDTree"]) {
    const key = PDFName.of(name),
      value = root.get(key);
    if (value instanceof PDFRef && !doc.context.lookup(value))
      root.set(key, PDFNull);
  }
}
