import {
  PDFDocument,
  PDFDict,
  PDFName,
  PDFRawStream,
  decodePDFRawStream,
} from "pdf-lib";
import { XMLParser, XMLBuilder, XMLValidator } from "fast-xml-parser";
import { LIMITS, validateSize } from "./contracts";
import { inspectPdf } from "../combine/generate";
import { normalizeOptionalTagIndexes } from "./optional-tag-indexes";
import { standardNamespaces } from "./standard-metadata";
const k = PDFName.of;
const namespaces = standardNamespaces;
type Node = Record<string, unknown>;
export function removeStandardDeclarations(xml: string) {
  if (/<!DOCTYPE|<!ENTITY/i.test(xml) || XMLValidator.validate(xml) !== true)
    throw Error("Invalid metadata");
  let changed = false;
  const tree = new XMLParser({
    preserveOrder: true,
    ignoreAttributes: false,
    processEntities: false,
    trimValues: false,
    parseTagValue: false,
  }).parse(xml) as Node[];
  function walk(nodes: Node[], inherited: Record<string, string>): Node[] {
    return nodes.flatMap((node) => {
      const attrs = { ...(node[":@"] as Record<string, string> | undefined) },
        scope = { ...inherited };
      for (const [name, value] of Object.entries(attrs))
        if (name === "@_xmlns") scope[""] = value;
        else if (name.startsWith("@_xmlns:")) scope[name.slice(8)] = value;
      const standard = (name: string, attribute = false) => {
        const parts = name.split(":");
        return namespaces.has(
          scope[
            parts.length > 1 ? parts[0]! : attribute ? "__attribute__" : ""
          ] ?? "",
        );
      };
      const tag = Object.keys(node).find((name) => name !== ":@")!;
      if (standard(tag)) {
        changed = true;
        return [];
      }
      for (const name of Object.keys(attrs)) {
        if (
          (name.startsWith("@_xmlns") && namespaces.has(attrs[name]!)) ||
          (!name.startsWith("@_xmlns") && standard(name.slice(2), true))
        ) {
          delete attrs[name];
          changed = true;
        }
      }
      const result: Node = { ...node };
      if (Array.isArray(node[tag]))
        result[tag] = walk(node[tag] as Node[], scope);
      if (node[":@"]) result[":@"] = attrs;
      return [result];
    });
  }
  const output = walk(tree, {});
  return {
    changed,
    xml: new XMLBuilder({
      preserveOrder: true,
      ignoreAttributes: false,
      processEntities: false,
      format: false,
    }).build(output) as string,
  };
}
export async function prepareOrdinaryCopy(
  bytes: Uint8Array,
  confirmed: boolean,
) {
  validateSize(bytes.length);
  const doc = await PDFDocument.load(bytes, {
    updateMetadata: false,
    throwOnInvalidObject: true,
  });
  if (Reflect.get(doc.context, "smartworksAmbiguousDictionary"))
    throw Error("Ambiguous PDF dictionaries");
  normalizeOptionalTagIndexes(doc);
  let changed = false;
  for (const [ref, obj] of doc.context.enumerateIndirectObjects()) {
    if (
      !(obj instanceof PDFRawStream) ||
      obj.dict.get(k("Type")) !== k("Metadata")
    )
      continue;
    const decoded = decodePDFRawStream(obj).getBytes(LIMITS.metadataBytes + 1);
    if (decoded.length > LIMITS.metadataBytes)
      throw Error("Metadata too large");
    let payload = decoded;
    if (new TextDecoder().decode(decoded.subarray(0, 9)) === "<?xpacket")
      for (let i = 9; i < Math.min(decoded.length - 1, 1024); i++)
        if (decoded[i] === 63 && decoded[i + 1] === 62) {
          payload = decoded.subarray(i + 2);
          break;
        }
    const result = removeStandardDeclarations(
      new TextDecoder("utf-8", { fatal: true }).decode(payload),
    );
    if (result.changed) {
      const dict = obj.dict.clone();
      dict.delete(k("Filter"));
      dict.delete(k("DecodeParms"));
      doc.context.assign(
        ref,
        PDFRawStream.of(dict, new TextEncoder().encode(result.xml)),
      );
      changed = true;
    }
  }
  const info = doc.context.lookup(doc.context.trailerInfo.Info);
  if (info instanceof PDFDict)
    for (const key of info.keys())
      if (
        ["GTS_PDFXVersion", "GTS_PDFXConformance", "GTS_PDFA1Version"].includes(
          key.decodeText(),
        )
      ) {
        info.delete(key);
        changed = true;
      }
  if (!changed) throw Error("No supported standard declaration");
  // Preserve the complete output intent and ICC profile; neither is a claim of compliance.
  const output = await doc.save();
  validateSize(output.length);
  const check = await inspectPdf(output);
  if (!check.ok)
    throw Error(
      `Ordinary copy failed validation: ${check.reason ?? check.code}${check.detail ? ": " + check.detail : ""}`,
    );
  if (check.pages !== doc.getPageCount())
    throw Error("Ordinary copy page count mismatch");
  return confirmed ? output : null;
}
