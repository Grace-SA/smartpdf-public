import {
  PDFDocument,
  PDFDict,
  PDFName,
  PDFString,
  PDFHexString,
  PDFRawStream,
  PDFObject,
  PDFObjectCopier,
  PDFRef,
} from "pdf-lib";
import { ProbeFailure } from "../core/contracts";
import { reader, key } from "./structure";

export function inspectAttachments(doc: PDFDocument) {
  const r = reader(doc, "attachments"),
    names = doc.catalog.lookupMaybe(key("Names"), PDFDict);
  const files = new Map<PDFDict, PDFObject>();
  const streams = new Set<PDFDict>();
  const string = (v: PDFObject | undefined) => {
    const s = r.resolve(v);
    if (!(s instanceof PDFString || s instanceof PDFHexString))
      return r.fail("An attachment has an invalid filename or description.");
    return s;
  };
  function file(raw: PDFObject): PDFDict {
    const d = r.dict(raw);
    if (r.name(d.get(key("AFRelationship"))) === "C2PA_Manifest")
      throw new ProbeFailure("UNSUPPORTED_PDF", "signature");
    if (files.has(d)) return d;
    if (files.size >= 100)
      r.fail("Use at most 100 embedded attachments per input.");
    r.keys(d, ["Type", "F", "UF", "EF", "Desc", "AFRelationship", "Subtype"]);
    if (d.has(key("Type")) && r.name(d.get(key("Type"))) !== "Filespec")
      r.fail("Invalid file specification.");
    if (!d.has(key("F")) && !d.has(key("UF")))
      r.fail("An attachment has no filename.");
    for (const n of ["F", "UF", "Desc"])
      if (d.has(key(n))) string(d.get(key(n)));
    if (
      d.has(key("AFRelationship")) &&
      !(r.resolve(d.get(key("AFRelationship"))) instanceof PDFName)
    )
      r.fail("Invalid associated-file relationship.");
    if (
      d.has(key("Subtype")) &&
      !(r.resolve(d.get(key("Subtype"))) instanceof PDFName)
    )
      r.fail("Invalid attachment subtype.");
    const ef = r.dict(d.get(key("EF")));
    r.keys(ef, ["F", "UF"]);
    if (!ef.keys().length)
      r.fail("External file references are not embedded attachments.");
    for (const [, v] of ef.entries()) {
      const stream = r.resolve(v);
      if (
        !(stream instanceof PDFRawStream) ||
        r.name(stream.dict.get(key("Type"))) !== "EmbeddedFile"
      )
        r.fail("An attachment payload is missing.");
      streams.add((stream as PDFRawStream).dict);
    }
    files.set(d, raw);
    return d;
  }
  const entries: { name: string; file: PDFDict }[] = [],
    seen = new Set<PDFDict>(),
    keys = new Set<string>();
  function tree(raw: PDFObject, depth = 0) {
    const d = r.dict(raw);
    if (depth > 100 || seen.has(d) || seen.size > 50000)
      r.fail("Invalid attachment name tree.");
    seen.add(d);
    r.keys(d, ["Names", "Kids", "Limits"]);
    if (d.has(key("Names")) === d.has(key("Kids")))
      r.fail("Ambiguous attachment name tree.");
    if (d.has(key("Names"))) {
      const values = r.array(d.get(key("Names")));
      if (values.length % 2) r.fail("Invalid attachment entries.");
      for (let i = 0; i < values.length; i += 2) {
        const name = string(values[i]).decodeText();
        if (keys.has(name)) r.fail("Duplicate attachment names.");
        keys.add(name);
        entries.push({ name, file: file(values[i + 1]!) });
      }
    } else for (const v of r.array(d.get(key("Kids")))) tree(v, depth + 1);
  }
  const embedded = names?.get(key("EmbeddedFiles"));
  if (embedded) tree(embedded);
  const associated = doc.catalog.has(key("AF"))
    ? r.array(doc.catalog.get(key("AF"))).map(file)
    : [];
  return { files, streams, names, entries, associated };
}

export function copyAttachments(
  output: PDFDocument,
  plan: ReturnType<typeof inspectAttachments>,
  copier: PDFObjectCopier,
  input: number,
) {
  const refs = new Map<PDFDict, PDFRef>();
  for (const [d, raw] of plan.files) {
    const copy = copier.copy(raw);
    refs.set(d, copy instanceof PDFRef ? copy : output.context.register(copy));
  }
  return {
    names: plan.entries.map((e) => ({
      name: `document-${input + 1}:${e.name}`,
      ref: refs.get(e.file)!,
    })),
    associated: plan.associated.map((d) => refs.get(d)!),
  };
}

export function finishAttachments(
  output: PDFDocument,
  parts: ReturnType<typeof copyAttachments>[],
) {
  const entries = parts
    .flatMap((p) => p.names)
    .sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
  if (entries.length) {
    const names =
      output.catalog.lookupMaybe(key("Names"), PDFDict) ??
      output.context.obj({});
    names.set(
      key("EmbeddedFiles"),
      output.context.obj({
        Names: entries.flatMap((e) => [PDFHexString.fromText(e.name), e.ref]),
      }),
    );
    output.catalog.set(key("Names"), names);
  }
  const associated = parts.flatMap((p) => p.associated);
  if (associated.length) {
    output.catalog.set(key("AF"), output.context.obj(associated));
    output.catalog.set(key("Version"), key("2.0"));
  }
}
