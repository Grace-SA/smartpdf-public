import {
  PDFDocument,
  PDFDict,
  PDFArray,
  PDFName,
  PDFObject,
  PDFRef,
  PDFRawStream,
  PDFString,
  PDFHexString,
  PDFNumber,
  decodePDFRawStream,
} from "pdf-lib";
import { LIMITS, validateSize } from "./contracts";
import { inspectPdf } from "../combine/generate";

const key = PDFName.of;
export const credentialCopyError =
  "A copy without Content Credentials could not be prepared safely. Your original PDF is unchanged.";

/** Only document-level C2PA attachments are eligible. All other signatures and
 * unsupported references still pass through the normal editing validator. */
export async function prepareCredentialCopy(
  bytes: Uint8Array,
  confirmed: boolean,
) {
  validateSize(bytes.length);
  const doc = await PDFDocument.load(bytes, {
    updateMetadata: false,
    throwOnInvalidObject: true,
  });
  if (Reflect.get(doc.context, "smartworksAmbiguousDictionary"))
    throw Error(credentialCopyError);
  const resolve = (value: PDFObject | undefined) =>
    value ? doc.context.lookup(value) : undefined;
  const inspected = new Set<PDFObject>();
  function sourceCheck(raw: PDFObject, depth = 0) {
    const obj = resolve(raw);
    if (!obj) throw Error(credentialCopyError);
    if (inspected.has(obj)) return;
    if (depth > LIMITS.depth || inspected.size >= LIMITS.nodes)
      throw Error(credentialCopyError);
    inspected.add(obj);
    if (obj instanceof PDFArray)
      for (const v of obj.asArray()) sourceCheck(v, depth + 1);
    const d =
      obj instanceof PDFRawStream
        ? obj.dict
        : obj instanceof PDFDict
          ? obj
          : undefined;
    if (!d) return;
    if (
      ["ByteRange", "DocMDP", "Perms"].some((n) => d.has(key(n))) ||
      ["Sig", "DocTimeStamp"].includes(
        String(resolve(d.get(key("Type")))).replace(/^\//, ""),
      ) ||
      resolve(d.get(key("FT"))) === key("Sig")
    )
      throw Error(credentialCopyError);
    const flags = resolve(d.get(key("SigFlags")));
    if (flags && (!(flags instanceof PDFNumber) || flags.asNumber() !== 0))
      throw Error(credentialCopyError);
    if (
      obj instanceof PDFRawStream &&
      resolve(d.get(key("Type"))) === key("Metadata")
    ) {
      const decoded = decodePDFRawStream(obj).getBytes(
        LIMITS.metadataBytes + 1,
      );
      if (
        decoded.length > LIMITS.metadataBytes ||
        /provenance|c2pa/i.test(new TextDecoder().decode(decoded))
      )
        throw Error(credentialCopyError);
    }
    for (const [, v] of d.entries()) sourceCheck(v, depth + 1);
  }
  const objects = doc.context.enumerateIndirectObjects();
  if (objects.length > LIMITS.objects) throw Error(credentialCopyError);
  for (const [, obj] of objects) sourceCheck(obj);
  const manifests = new Set<PDFDict>();
  const isManifest = (raw: PDFObject) => {
    const d = resolve(raw);
    return (
      d instanceof PDFDict &&
      resolve(d.get(key("AFRelationship"))) === key("C2PA_Manifest")
    );
  };
  const associated = resolve(doc.catalog.get(key("AF")));
  if (!(associated instanceof PDFArray)) throw Error(credentialCopyError);
  for (const raw of associated.asArray())
    if (isManifest(raw)) manifests.add(resolve(raw) as PDFDict);
  if (!manifests.size) throw Error(credentialCopyError);
  const remaining = associated
    .asArray()
    .filter((raw) => !manifests.has(resolve(raw) as PDFDict));
  if (remaining.length) doc.catalog.set(key("AF"), doc.context.obj(remaining));
  else doc.catalog.delete(key("AF"));
  const names = doc.catalog.lookupMaybe(key("Names"), PDFDict);
  const tree = names?.get(key("EmbeddedFiles"));
  const seenTrees = new Set<PDFDict>();
  const retained: PDFObject[] = [];
  const removed = new Set<PDFDict>();
  function walk(raw: PDFObject, depth = 0) {
    const d = resolve(raw);
    if (
      !(d instanceof PDFDict) ||
      seenTrees.has(d) ||
      depth > LIMITS.depth ||
      seenTrees.size > LIMITS.objects
    )
      throw Error(credentialCopyError);
    seenTrees.add(d);
    if (
      d
        .keys()
        .some((k) => !["Names", "Kids", "Limits"].includes(k.decodeText()))
    )
      throw Error(credentialCopyError);
    const entries = resolve(d.get(key("Names"))),
      kids = resolve(d.get(key("Kids")));
    if ((entries !== undefined) === (kids !== undefined))
      throw Error(credentialCopyError);
    if (entries instanceof PDFArray) {
      const values = entries.asArray();
      if (values.length % 2) throw Error(credentialCopyError);
      for (let i = 0; i < values.length; i += 2) {
        const name = resolve(values[i]);
        if (!(name instanceof PDFString || name instanceof PDFHexString))
          throw Error(credentialCopyError);
        const file = resolve(values[i + 1]);
        if (manifests.has(file as PDFDict)) removed.add(file as PDFDict);
        else retained.push(values[i]!, values[i + 1]!);
      }
    } else if (kids instanceof PDFArray)
      for (const child of kids.asArray()) walk(child, depth + 1);
    else throw Error(credentialCopyError);
  }
  if (tree) walk(tree);
  if (removed.size !== manifests.size) throw Error(credentialCopyError);
  if (retained.length)
    names!.set(key("EmbeddedFiles"), doc.context.obj({ Names: retained }));
  else names!.delete(key("EmbeddedFiles"));
  if (!names!.keys().length) doc.catalog.delete(key("Names"));

  const refs = new Set<PDFRef>(),
    seen = new Set<PDFObject>();
  function visit(raw: PDFObject, depth = 0) {
    if (raw instanceof PDFRef) refs.add(raw);
    const object = resolve(raw);
    if (!object || manifests.has(object as PDFDict))
      throw Error(credentialCopyError);
    if (seen.has(object)) return;
    if (depth > LIMITS.depth || seen.size >= LIMITS.nodes)
      throw Error(credentialCopyError);
    seen.add(object);
    if (object instanceof PDFArray)
      for (const v of object.asArray()) visit(v, depth + 1);
    const d =
      object instanceof PDFRawStream
        ? object.dict
        : object instanceof PDFDict
          ? object
          : undefined;
    if (d) for (const [, v] of d.entries()) visit(v, depth + 1);
  }
  if (doc.context.trailerInfo.Root) visit(doc.context.trailerInfo.Root);
  if (doc.context.trailerInfo.Info) visit(doc.context.trailerInfo.Info);
  // Fresh serialization excludes previous incremental revisions and detached payloads.
  for (const [ref] of doc.context.enumerateIndirectObjects())
    if (!refs.has(ref)) doc.context.delete(ref);
  const output = await doc.save();
  validateSize(output.length);
  const check = await inspectPdf(output);
  if (!check.ok || check.pages !== doc.getPageCount())
    throw Error(credentialCopyError);
  // Detection does not return a modified PDF; only explicit confirmation does.
  return confirmed ? output : null;
}
