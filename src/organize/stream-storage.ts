import {
  PDFDocument,
  PDFRawStream,
  PDFArray,
  PDFName,
  decodePDFRawStream,
} from "pdf-lib";
const k = PDFName.of;
/** Remove only an ASCII85 transport wrapper. The inner compressed payload and
 * its image/content codec stay byte-for-byte intact: no raster re-encoding. */
export function compactStreamStorage(doc: PDFDocument) {
  for (const [ref, object] of doc.context.enumerateIndirectObjects()) {
    if (!(object instanceof PDFRawStream) || object.dict.has(k("DecodeParms")))
      continue;
    const filters = doc.context.lookup(object.dict.get(k("Filter")));
    if (
      !(filters instanceof PDFArray) ||
      filters.size() < 2 ||
      doc.context.lookup(filters.get(0)) !== k("ASCII85Decode")
    )
      continue;
    const wrapper = doc.context.obj({ Filter: "ASCII85Decode" });
    let payload: Uint8Array;
    try {
      payload = decodePDFRawStream(
        PDFRawStream.of(wrapper, object.contents),
      ).decode();
    } catch {
      continue;
    } // Optional storage optimization must not expand supported limits.
    if (payload.length >= object.contents.length) continue;
    const dict = object.dict.clone();
    const remaining = filters.asArray().slice(1);
    dict.set(
      k("Filter"),
      remaining.length === 1 ? remaining[0]! : doc.context.obj(remaining),
    );
    doc.context.assign(ref, PDFRawStream.of(dict, payload));
  }
}
