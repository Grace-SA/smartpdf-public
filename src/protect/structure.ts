import {
  PDFDocument,
  PDFName,
  PDFDict,
  PDFArray,
  PDFRef,
  PDFRawStream,
  PDFString,
  PDFHexString,
  PDFObject,
  decodePDFRawStream,
} from "pdf-lib";
import { LIMITS } from "../core/contracts";
import { inspectPdf } from "../combine/generate";
import { ProtectFailure } from "./model";

const key = PDFName.of;
function decoded(stream: PDFRawStream) {
  const reader = decodePDFRawStream(stream);
  const chunks: (Uint8Array | Uint8ClampedArray)[] = [];
  let total = 0;
  while (true) {
    const chunk = reader.getBytes(64 * 1024);
    total += chunk.length;
    if (total >= LIMITS.decodedStreamBytes)
      throw new ProtectFailure("RESOURCE");
    chunks.push(chunk);
    if (chunk.length < 64 * 1024) break;
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.length;
  }
  return bytes;
}
const hex = (bytes: Uint8Array) =>
  Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");

/** Compare logical reachable structure, independent of object numbering,
 * compression, dictionary ordering and stream Length serialization. */
export async function structureDigest(bytes: Uint8Array): Promise<string> {
  const doc = await PDFDocument.load(bytes, {
    updateMetadata: false,
    throwOnInvalidObject: true,
  });
  // qpdf adds the Adobe extension declaration required for revision-6
  // encryption. Only this exact declaration is an expected structural change.
  const extensions = doc.catalog.lookupMaybe(key("Extensions"), PDFDict);
  const adobe = extensions?.lookupMaybe(key("ADBE"), PDFDict);
  if (adobe) {
    if (
      adobe.keys().length !== 2 ||
      String(adobe.get(key("BaseVersion"))) !== "/1.7" ||
      String(adobe.get(key("ExtensionLevel"))) !== "8"
    )
      throw new ProtectFailure("INPUT");
    extensions!.delete(key("ADBE"));
    if (!extensions!.keys().length) doc.catalog.delete(key("Extensions"));
  }
  const seen = new Map<PDFObject, number>();
  let decodedTotal = 0;
  let nodes = 0;
  async function walk(raw: PDFObject | undefined, depth = 0): Promise<unknown> {
    if (!raw) return null;
    if (++nodes > LIMITS.nodes || depth > LIMITS.depth)
      throw new ProtectFailure("RESOURCE");
    const obj = raw instanceof PDFRef ? doc.context.lookup(raw) : raw;
    if (!obj) throw new ProtectFailure("INPUT");
    if (
      obj instanceof PDFDict ||
      obj instanceof PDFArray ||
      obj instanceof PDFRawStream
    ) {
      if (seen.has(obj)) return ["ref", seen.get(obj)];
      seen.set(obj, seen.size);
    }
    if (obj instanceof PDFArray) {
      const values: unknown[] = [];
      for (const child of obj.asArray())
        values.push(await walk(child, depth + 1));
      return ["array", values];
    }
    if (obj instanceof PDFDict || obj instanceof PDFRawStream) {
      const dict = obj instanceof PDFRawStream ? obj.dict : obj;
      const entries: unknown[] = [];
      const isStream = obj instanceof PDFRawStream;
      const filters = dict.get(key("Filter"));
      const simple =
        !filters ||
        ["/FlateDecode", "/ASCIIHexDecode", "/ASCII85Decode"].includes(
          String(filters),
        );
      for (const [name, value] of dict
        .entries()
        .sort(([a], [b]) => a.toString().localeCompare(b.toString()))) {
        if (
          isStream &&
          (name.decodeText() === "Length" ||
            (simple && name.decodeText() === "Filter"))
        )
          continue;
        if (
          name.decodeText() === "AFRelationship" &&
          String(doc.context.lookup(value)) === "/C2PA_Manifest"
        )
          throw new ProtectFailure("INPUT");
        if (["EmbeddedFiles", "AF", "EF"].includes(name.decodeText()))
          throw new ProtectFailure("INPUT");
        entries.push([name.toString(), await walk(value, depth + 1)]);
      }
      if (isStream) {
        // Preserve encoded bytes for image codecs unsupported by pdf-lib;
        // qpdf is explicitly told to preserve stream data in this operation.
        // The locked pdf-lib patch enforces per-stream and document allocation
        // budgets. Do not request 8 MiB up front for every tiny page stream.
        const content = simple ? decoded(obj) : obj.contents;
        decodedTotal += content.length;
        if (
          content.length >= LIMITS.decodedStreamBytes ||
          decodedTotal > 128 * 1024 * 1024
        )
          throw new ProtectFailure("RESOURCE");
        if (
          String(dict.get(key("Type"))) === "/Metadata" &&
          /c2pa|provenance/i.test(new TextDecoder().decode(content))
        )
          throw new ProtectFailure("INPUT");
        const digest = await crypto.subtle.digest(
          "SHA-256",
          content.slice() as Uint8Array<ArrayBuffer>,
        );
        return [
          "stream",
          entries,
          simple ? null : String(filters),
          hex(new Uint8Array(digest)),
        ];
      }
      return ["dict", entries];
    }
    if (obj instanceof PDFString || obj instanceof PDFHexString)
      return ["string", hex(obj.asBytes())];
    return obj.toString();
  }
  const content = JSON.stringify([
    await walk(doc.catalog),
    await walk(doc.context.trailerInfo.Info),
  ]);
  return hex(
    new Uint8Array(
      await crypto.subtle.digest("SHA-256", new TextEncoder().encode(content)),
    ),
  );
}

export async function inspectProtect(bytes: Uint8Array) {
  const result = await inspectPdf(bytes);
  if (!result.ok)
    throw new ProtectFailure(
      result.code === "RESOURCE_LIMIT" ? "RESOURCE" : "INPUT",
    );
  const digest = await structureDigest(bytes);
  return { pages: result.pages, digest };
}

export async function verifyEncryption(bytes: Uint8Array) {
  // Only inspect the unencrypted security dictionary here. Never use
  // ignoreEncryption to treat encrypted document content as decrypted.
  const doc = await PDFDocument.load(bytes, {
    ignoreEncryption: true,
    updateMetadata: false,
  });
  const enc = doc.context.lookup(doc.context.trailerInfo.Encrypt);
  if (!(enc instanceof PDFDict)) throw new ProtectFailure("VERIFY");
  const cf = enc.lookup(key("CF"), PDFDict);
  const std = cf.lookup(key("StdCF"), PDFDict);
  if (
    String(enc.get(key("Filter"))) !== "/Standard" ||
    String(enc.get(key("V"))) !== "5" ||
    String(enc.get(key("R"))) !== "6" ||
    String(enc.get(key("Length"))) !== "256" ||
    String(std.get(key("CFM"))) !== "/AESV3" ||
    String(enc.get(key("StmF"))) !== "/StdCF" ||
    String(enc.get(key("StrF"))) !== "/StdCF" ||
    String(enc.get(key("EncryptMetadata"))) === "false"
  )
    throw new ProtectFailure("VERIFY");
}
