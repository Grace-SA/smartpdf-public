import {
  PDFDocument,
  PDFDict,
  PDFArray,
  PDFName,
  PDFString,
  PDFHexString,
  PDFNumber,
  PDFRef,
  PDFObjectCopier,
} from "pdf-lib";
import { ProbeFailure } from "./contracts";
import { formIdentity } from "./empty-form";
const k = PDFName.of;
export function flatForm(doc: PDFDocument) {
  const fail = (): never => {
    throw new ProbeFailure("UNSUPPORTED_PDF", "form");
  };
  const raw = doc.catalog.get(k("AcroForm"));
  if (!raw) return undefined;
  const form = doc.context.lookup(raw);
  if (!(form instanceof PDFDict)) return fail();
  if (form.keys().some((n) => !["Fields", "DA", "DR"].includes(n.decodeText())))
    return fail();
  const fields = doc.context.lookup(form.get(k("Fields")));
  if (!(fields instanceof PDFArray) || fields.size() > 1000) return fail();
  if (form.has(k("DA"))) {
    const v = doc.context.lookup(form.get(k("DA")));
    if (!(v instanceof PDFString || v instanceof PDFHexString)) return fail();
  }
  if (
    form.has(k("DR")) &&
    !(doc.context.lookup(form.get(k("DR"))) instanceof PDFDict)
  )
    return fail();
  const widgets = new Set<PDFDict>(),
    names = new Set<string>();
  for (const ref of fields.asArray()) {
    const d = doc.context.lookup(ref);
    if (!(ref instanceof PDFRef) || !(d instanceof PDFDict) || widgets.has(d))
      return fail();
    const type = doc.context.lookup(d.get(k("FT"))),
      subtype = doc.context.lookup(d.get(k("Subtype"))),
      name = doc.context.lookup(d.get(k("T")));
    if (
      !(type instanceof PDFName) ||
      !["Tx", "Btn"].includes(type.decodeText()) ||
      subtype !== k("Widget") ||
      d.has(k("Parent")) ||
      d.has(k("Kids"))
    )
      return fail();
    if (
      !(name instanceof PDFString || name instanceof PDFHexString) ||
      !name.decodeText() ||
      names.has(name.decodeText())
    )
      return fail();
    const flags = doc.context.lookup(d.get(k("Ff")));
    if (
      flags &&
      (!(flags instanceof PDFNumber) ||
        !Number.isSafeInteger(flags.asNumber()) ||
        flags.asNumber() < 0 ||
        (flags.asNumber() & 65536) !== 0)
    )
      return fail();
    names.add(name.decodeText());
    widgets.add(d);
  }
  const owners = new Set<PDFDict>();
  for (const page of doc.getPages()) {
    const ann = doc.context.lookup(page.node.get(k("Annots")));
    if (!ann) continue;
    if (!(ann instanceof PDFArray)) return fail();
    for (const ref of ann.asArray()) {
      const d = doc.context.lookup(ref);
      if (
        !(d instanceof PDFDict) ||
        doc.context.lookup(d.get(k("Subtype"))) !== k("Widget")
      )
        continue;
      if (!widgets.has(d) || owners.has(d)) return fail();
      owners.add(d);
    }
  }
  if (owners.size !== widgets.size) return fail();
  const settings = form.clone();
  settings.set(k("Fields"), doc.context.obj([]));
  return { form, widgets, names, identity: formIdentity(doc, settings) };
}

export function preserveFlatForm(
  output: PDFDocument,
  source: PDFDocument,
  copier: PDFObjectCopier,
  annotations: Map<PDFDict, PDFRef>,
  state: { identity?: string; names: Set<string> },
) {
  const plan = flatForm(source);
  if (!plan) return;
  if (state.identity !== undefined && state.identity !== plan.identity)
    throw new Error(
      "These PDFs have different form defaults. Combine them separately to preserve their appearance and editing settings.",
    );
  for (const name of plan.names)
    if (state.names.has(name))
      throw new Error(
        "These PDFs contain fields with the same name. Combine them separately to keep their values independent.",
      );
  let form = output.catalog.lookupMaybe(k("AcroForm"), PDFDict);
  if (!form) {
    form = PDFDict.withContext(output.context);
    for (const [name, v] of plan.form.entries())
      if (name !== k("Fields")) form.set(name, copier.copy(v));
    form.set(k("Fields"), output.context.obj([]));
    output.catalog.set(k("AcroForm"), form);
  }
  const fields = form.lookup(k("Fields"), PDFArray);
  for (const widget of plan.widgets) {
    const ref = annotations.get(widget);
    if (!ref) throw new Error("A form field lost its page annotation.");
    fields.push(ref);
  }
  state.identity = plan.identity;
  for (const name of plan.names) state.names.add(name);
}
