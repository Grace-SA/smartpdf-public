import {
  PDFDocument,
  PDFDict,
  PDFArray,
  PDFName,
  PDFString,
  PDFHexString,
  PDFRawStream,
  PDFObjectCopier,
  decodePDFRawStream,
} from "pdf-lib";
import { ProbeFailure } from "../core/contracts";
import { formIdentity } from "../core/empty-form";
const k = PDFName.of;
export function outputIntents(doc: PDFDocument) {
  const raw = doc.catalog.get(k("OutputIntents"));
  if (!raw) return undefined;
  const fail = (): never => {
    throw new ProbeFailure("UNSUPPORTED_PDF", "standard");
  };
  const a = doc.context.lookup(raw);
  if (!(a instanceof PDFArray) || a.size() !== 1) return fail();
  const d = doc.context.lookup(a.get(0));
  if (!(d instanceof PDFDict)) return fail();
  if (
    d
      .keys()
      .some(
        (n) =>
          ![
            "Type",
            "S",
            "OutputCondition",
            "OutputConditionIdentifier",
            "RegistryName",
            "Info",
            "DestOutputProfile",
          ].includes(n.decodeText()),
      )
  )
    return fail();
  if (d.has(k("Type")) && d.get(k("Type")) !== k("OutputIntent")) return fail();
  const subtype = d.get(k("S"));
  if (subtype && subtype !== k("GTS_PDFA1") && subtype !== k("GTS_PDFX"))
    return fail();
  for (const name of [
    "OutputCondition",
    "OutputConditionIdentifier",
    "RegistryName",
    "Info",
  ]) {
    const v = doc.context.lookup(d.get(k(name)));
    if (
      (name === "OutputConditionIdentifier" || v) &&
      !(v instanceof PDFString || v instanceof PDFHexString)
    )
      return fail();
  }
  const profile = doc.context.lookup(d.get(k("DestOutputProfile")));
  if (!profile && subtype === k("GTS_PDFX")) {
    // A registered printing condition may describe the intent without an ICC
    // stream. Preserve its exact dictionary; do not infer or download a profile.
    const wrapper = doc.context.obj({ OutputIntents: a });
    return { array: a, identity: formIdentity(doc, wrapper) };
  }
  if (!(profile instanceof PDFRawStream)) return fail();
  const data = decodePDFRawStream(profile).decode();
  if (
    data.length < 128 ||
    data.length > 1048576 ||
    new TextDecoder().decode(data.slice(36, 40)) !== "acsp"
  )
    return fail();
  const wrapper = doc.context.obj({ OutputIntents: a });
  return { array: a, identity: formIdentity(doc, wrapper) };
}
function colorNeutral(doc: PDFDocument) {
  for (const p of doc.getPages()) {
    const annotations = doc.context.lookup(p.node.get(k("Annots")));
    if (
      annotations &&
      (!(annotations instanceof PDFArray) || annotations.size())
    )
      return false;
    const raw = doc.context.lookup(p.node.get(k("Contents")));
    const contents = raw instanceof PDFArray ? raw.asArray() : raw ? [raw] : [];
    for (const v of contents) {
      const stream = doc.context.lookup(v);
      if (
        !(stream instanceof PDFRawStream) ||
        new TextDecoder().decode(decodePDFRawStream(stream).decode()).trim()
      )
        return false;
    }
  }
  return true;
}
export function preserveOutputIntents(
  output: PDFDocument,
  source: PDFDocument,
  copier: PDFObjectCopier,
  state: { identity?: string; unprofiledContent: boolean },
) {
  const plan = outputIntents(source);
  if (plan) {
    if (
      state.unprofiledContent ||
      (state.identity !== undefined && state.identity !== plan.identity)
    )
      throw new Error(
        "These PDFs have different output colour settings. Combine files with the same colour profile separately to preserve their intended colours.",
      );
    if (state.identity === undefined)
      output.catalog.set(k("OutputIntents"), copier.copy(plan.array));
    state.identity = plan.identity;
  } else if (!colorNeutral(source)) {
    if (state.identity !== undefined)
      throw new Error(
        "A PDF without an output colour profile cannot be mixed with this profiled PDF without changing its colour settings.",
      );
    state.unprofiledContent = true;
  }
}
