import {
  PDFDocument,
  PDFDict,
  PDFArray,
  PDFName,
  PDFString,
  PDFHexString,
  PDFObject,
  PDFRef,
  PDFRawStream,
  PDFObjectCopier,
} from "pdf-lib";
const key = PDFName.of;
// An empty form container is not an interactive form. Unknown settings, actual
// fields and widgets remain subject to the normal fail-closed preflight.
export function emptyForm(doc: PDFDocument): PDFDict | undefined {
  const form = doc.context.lookup(doc.catalog.get(key("AcroForm")));
  if (!(form instanceof PDFDict)) return undefined;
  if (form.keys().some((k) => !["Fields", "DA", "DR"].includes(k.decodeText())))
    return undefined;
  const fields = doc.context.lookup(form.get(key("Fields")));
  if (!(fields instanceof PDFArray) || fields.size() !== 0) return undefined;
  if (form.has(key("DA"))) {
    const da = doc.context.lookup(form.get(key("DA")));
    if (!(da instanceof PDFString || da instanceof PDFHexString))
      return undefined;
  }
  if (
    form.has(key("DR")) &&
    !(doc.context.lookup(form.get(key("DR"))) instanceof PDFDict)
  )
    return undefined;
  return form;
}

export function formIdentity(doc: PDFDocument, form: PDFDict): string {
  let budget = 1_048_576;
  const active = new Set<PDFObject>();
  function value(raw: PDFObject | undefined, depth = 0): unknown {
    const obj = raw instanceof PDFRef ? doc.context.lookup(raw) : raw;
    if (!obj || depth > 100 || active.has(obj) || --budget < 0)
      throw new Error("Empty form settings cannot be preserved safely.");
    active.add(obj);
    try {
      if (obj instanceof PDFRawStream) {
        budget -= obj.contents.length;
        if (budget < 0)
          throw new Error(
            "Empty form settings are too large to compare safely.",
          );
        return ["stream", value(obj.dict, depth + 1), Array.from(obj.contents)];
      }
      if (obj instanceof PDFDict)
        return obj
          .entries()
          .sort(([a], [b]) => a.toString().localeCompare(b.toString()))
          .map(([k, v]) => [k.toString(), value(v, depth + 1)]);
      if (obj instanceof PDFArray)
        return obj.asArray().map((v) => value(v, depth + 1));
      const text = obj.toString();
      budget -= text.length;
      if (budget < 0)
        throw new Error("Empty form settings are too large to compare safely.");
      return text;
    } finally {
      active.delete(obj);
    }
  }
  return JSON.stringify(value(form));
}

export function preserveEmptyForm(
  output: PDFDocument,
  source: PDFDocument,
  copier: PDFObjectCopier,
  previous: string | undefined,
): string | undefined {
  const form = emptyForm(source);
  if (!form) return previous;
  const identity = formIdentity(source, form);
  if (previous !== undefined && previous !== identity)
    throw new Error(
      "These PDFs have different empty form settings. Combine them separately to preserve their settings.",
    );
  if (previous === undefined)
    output.catalog.set(key("AcroForm"), copier.copy(form));
  return identity;
}
