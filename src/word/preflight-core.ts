import { Inflate } from "pako";
import { XMLParser, XMLValidator } from "fast-xml-parser";

export type InputIssue = { code: string; message: string };
export type WordCheck = {
  issues: InputIssue[];
  warnings: string[];
  revisions: boolean;
  originalViewUnsupported: boolean;
  comments: boolean;
  fonts: string[];
  complexLayout: boolean;
};
const W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
const messages: Record<string, string> = {
  STRUCTURAL_REVISIONS:
    "Resolve table row, cell or paragraph structure revisions in Word before converting.",
  INVALID_DOCX: "Choose a valid, unencrypted DOCX document.",
  UNSAFE_PACKAGE: "Protected or unsafe document package.",
  PACKAGE_LIMIT: "Document expands beyond the processing limit.",
  MALFORMED_XML:
    "The document contains malformed XML. Open it in Word and save a new DOCX copy.",
  TRACKED_CHANGES:
    "Accept or reject tracked changes in Word before converting.",
  COMMENTS: "Remove document comments in Word before converting.",
  HIDDEN_TEXT: "Show or remove hidden text in Word before converting.",
  EMBEDDED_OBJECTS:
    "Remove embedded files or objects in Word before converting.",
  EMBEDDED_FONTS:
    "Save a copy without embedded fonts in Word before converting.",
  MACROS: "Save a macro-free DOCX in Word before converting.",
  ACTIVE_CONTENT: "Remove active controls in Word before converting.",
  EXTERNAL_CONTENT:
    "Embed linked content or remove linked templates in Word before converting.",
  EXTERNAL_DATA_FIELDS:
    "Remove external data fields in Word before converting.",
  STRUCTURE_LIMIT: "Document structure exceeds the processing limit.",
  EMPTY_DOCUMENT: "The document has no visible content to convert.",
};
class Invalid extends Error {
  constructor(readonly code: string) {
    super(messages[code]);
  }
}
const table = new Uint32Array(256);
for (let n = 0; n < 256; n++) {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  table[n] = c >>> 0;
}
export function crc32(bytes: Uint8Array): number {
  let c = 0xffffffff;
  for (const b of bytes) c = table[(c ^ b) & 255]! ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
type Entry = {
  name: string;
  start: number;
  size: number;
  raw: number;
  method: number;
  crc: number;
};
function entries(bytes: Uint8Array): Entry[] {
  if (bytes.length < 22 || bytes.length > 30 * 1048576)
    throw new Invalid("INVALID_DOCX");
  const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let end = -1;
  for (let n = bytes.length - 22; n >= Math.max(0, bytes.length - 65557); n--)
    if (
      v.getUint32(n, true) === 0x06054b50 &&
      n + 22 + v.getUint16(n + 20, true) === bytes.length
    ) {
      end = n;
      break;
    }
  if (end < 0 || v.getUint16(end + 4, true) || v.getUint16(end + 6, true))
    throw new Invalid("INVALID_DOCX");
  const count = v.getUint16(end + 10, true),
    centralSize = v.getUint32(end + 12, true),
    central = v.getUint32(end + 16, true);
  if (
    !count ||
    count > 2000 ||
    count !== v.getUint16(end + 8, true) ||
    central + centralSize !== end
  )
    throw new Invalid("PACKAGE_LIMIT");
  const result: Entry[] = [],
    names = new Set<string>(),
    spans: [number, number][] = [];
  let p = central,
    total = 0;
  for (let i = 0; i < count; i++) {
    if (p + 46 > end || v.getUint32(p, true) !== 0x02014b50)
      throw new Invalid("INVALID_DOCX");
    const flags = v.getUint16(p + 8, true),
      method = v.getUint16(p + 10, true),
      size = v.getUint32(p + 20, true),
      raw = v.getUint32(p + 24, true),
      len = v.getUint16(p + 28, true);
    const next =
        p + 46 + len + v.getUint16(p + 30, true) + v.getUint16(p + 32, true),
      local = v.getUint32(p + 42, true);
    if (
      next > end ||
      flags & 1 ||
      ![0, 8].includes(method) ||
      local + 30 > central ||
      v.getUint32(local, true) !== 0x04034b50
    )
      throw new Invalid("UNSAFE_PACKAGE");
    const nameBytes = bytes.subarray(p + 46, p + 46 + len),
      name = new TextDecoder(flags & 0x800 ? "utf-8" : "latin1", {
        fatal: true,
      }).decode(nameBytes);
    if (
      names.has(name) ||
      name.includes("\\") ||
      name.startsWith("/") ||
      name.split("/").includes("..") ||
      name.includes("\0")
    )
      throw new Invalid("UNSAFE_PACKAGE");
    names.add(name);
    total += raw;
    if (
      total > 100 * 1048576 ||
      raw > 30 * 1048576 ||
      raw > Math.max(size, 1) * 200
    )
      throw new Invalid("PACKAGE_LIMIT");
    const localLen = v.getUint16(local + 26, true),
      start = local + 30 + localLen + v.getUint16(local + 28, true);
    if (
      v.getUint16(local + 6, true) !== flags ||
      v.getUint16(local + 8, true) !== method ||
      localLen !== len ||
      start + size > central ||
      !nameBytes.every((b, n) => bytes[local + 30 + n] === b)
    )
      throw new Invalid("UNSAFE_PACKAGE");
    if (
      !(flags & 8) &&
      (v.getUint32(local + 14, true) !== v.getUint32(p + 16, true) ||
        v.getUint32(local + 18, true) !== size ||
        v.getUint32(local + 22, true) !== raw)
    )
      throw new Invalid("UNSAFE_PACKAGE");
    if (method === 0 && size !== raw) throw new Invalid("INVALID_DOCX");
    spans.push([local, start + size]);
    result.push({
      name,
      start,
      size,
      raw,
      method,
      crc: v.getUint32(p + 16, true),
    });
    p = next;
  }
  if (
    p !== end ||
    spans
      .sort((a, b) => a[0] - b[0])
      .some((s, i, a) => i > 0 && s[0] < a[i - 1]![1])
  )
    throw new Invalid("UNSAFE_PACKAGE");
  return result;
}
function xmlBytes(bytes: Uint8Array, entry: Entry): Uint8Array {
  if (entry.raw > 8 * 1048576) throw new Invalid("PACKAGE_LIMIT");
  const input = bytes.subarray(entry.start, entry.start + entry.size);
  let output: Uint8Array;
  if (entry.method === 0) output = input;
  else {
    output = new Uint8Array(entry.raw);
    let offset = 0;
    const inflate = new Inflate({ raw: true, chunkSize: 32768 });
    inflate.onData = (chunk) => {
      if (offset + chunk.length > output.length)
        throw new Invalid("PACKAGE_LIMIT");
      output.set(chunk, offset);
      offset += chunk.length;
    };
    if (!inflate.push(input, true) || inflate.err || offset !== entry.raw)
      throw new Invalid("INVALID_DOCX");
  }
  if (output.length !== entry.raw || crc32(output) !== entry.crc)
    throw new Invalid("INVALID_DOCX");
  return output;
}
const revisions = new Set([
  "ins",
  "del",
  "delText",
  "moveFrom",
  "moveTo",
  "moveFromRangeStart",
  "moveFromRangeEnd",
  "moveToRangeStart",
  "moveToRangeEnd",
  "rPrChange",
  "pPrChange",
  "tblPrChange",
  "trPrChange",
  "tcPrChange",
  "sectPrChange",
  "tblGridChange",
  "numberingChange",
  "cellIns",
  "cellDel",
  "cellMerge",
]);
type Ordered = Record<string, unknown>;
function xmlPoint(n: number) {
  return (
    [9, 10, 13].includes(n) ||
    (n >= 32 && n <= 0xd7ff) ||
    (n >= 0xe000 && n <= 0xfffd) ||
    (n >= 0x10000 && n <= 0x10ffff)
  );
}
function strictXmlCharacters(text: string) {
  for (const char of text)
    if (!xmlPoint(char.codePointAt(0)!)) throw new Invalid("MALFORMED_XML");
  for (let i = 0; i < text.length; i++) {
    const skip = text.startsWith("<!--", i)
      ? (["-->", 4] as const)
      : text.startsWith("<![CDATA[", i)
        ? (["]]>", 9] as const)
        : text.startsWith("<?", i)
          ? (["?>", 2] as const)
          : null;
    if (skip) {
      const end = text.indexOf(skip[0], i + skip[1]);
      if (end < 0) throw new Invalid("MALFORMED_XML");
      i = end + skip[0].length - 1;
      continue;
    }
    if (text[i] !== "&") continue;
    const end = text.indexOf(";", i + 1);
    if (end < 0 || end - i > 32) throw new Invalid("MALFORMED_XML");
    const ref = text.slice(i + 1, end);
    if (!["amp", "lt", "gt", "apos", "quot"].includes(ref)) {
      if (
        !/^#(?:[0-9]+|x[0-9a-fA-F]+)$/.test(ref) ||
        !xmlPoint(
          Number.parseInt(
            ref.slice(ref[1] === "x" ? 2 : 1),
            ref[1] === "x" ? 16 : 10,
          ),
        )
      )
        throw new Invalid("MALFORMED_XML");
    }
    i = end;
  }
}
export function inspectWordBytes(bytes: Uint8Array): WordCheck {
  const codes = new Set<string>(),
    warnings = new Set<string>(),
    fonts = new Set<string>();
  let originalViewUnsupported = false;
  let complexLayout = false,
    nodes = 0,
    main = false,
    types = false,
    visible = false;
  const add = (code: string) => codes.add(code);
  try {
    const list = entries(bytes);
    for (const entry of list) {
      const lower = entry.name.toLowerCase();
      if (lower.includes("vbaproject")) add("MACROS");
      if (lower.includes("activex/") || lower.includes("customui/"))
        add("ACTIVE_CONTENT");
      if (lower.includes("embeddings/")) add("EMBEDDED_OBJECTS");
      if (lower.includes("fonts/")) add("EMBEDDED_FONTS");
      if (!lower.endsWith(".xml") && !lower.endsWith(".rels")) continue;
      const raw = xmlBytes(bytes, entry);
      const encoding =
        (raw[0] === 0xff && raw[1] === 0xfe) || (raw[0] === 60 && raw[1] === 0)
          ? "utf-16le"
          : (raw[0] === 0xfe && raw[1] === 0xff) ||
              (raw[0] === 0 && raw[1] === 60)
            ? "utf-16be"
            : "utf-8";
      const text = new TextDecoder(encoding, { fatal: true }).decode(raw);
      if (/<!\s*(DOCTYPE|ENTITY)/i.test(text))
        throw new Invalid("UNSAFE_PACKAGE");
      strictXmlCharacters(text);
      if ((text.match(/<[A-Za-z_:]/g)?.length || 0) + nodes > 200000)
        throw new Invalid("STRUCTURE_LIMIT");
      if (XMLValidator.validate(text) !== true)
        throw new Invalid("MALFORMED_XML");
      const tree = new XMLParser({
        preserveOrder: true,
        ignoreAttributes: false,
        processEntities: false,
        trimValues: false,
        parseTagValue: false,
      }).parse(text) as Ordered[];
      const stack: {
        items: Ordered[];
        parent?: string;
        ns: Record<string, string>;
        depth: number;
      }[] = [...tree].reverse().map((item) => ({
        items: [item],
        ns: { xml: "http://www.w3.org/XML/1998/namespace" },
        depth: 0,
      }));
      let fields = "";
      while (stack.length) {
        const frame = stack.pop()!;
        for (const item of frame.items) {
          const name = Object.keys(item).find(
            (k) => ![":@", "#text"].includes(k),
          );
          if (!name || name.startsWith("?")) {
            if (
              entry.name === "word/document.xml" &&
              String(item["#text"] || "").trim()
            )
              visible = true;
            continue;
          }
          if (++nodes > 200000 || frame.depth >= 64)
            throw new Invalid("STRUCTURE_LIMIT");
          const attrs = (item[":@"] || {}) as Record<string, string>,
            ns = { ...frame.ns };
          for (const [k, v] of Object.entries(attrs))
            if (k === "@_xmlns") ns[""] = v;
            else if (k.startsWith("@_xmlns:")) ns[k.slice(8)] = v;
          const parts = name.split(":"),
            local = parts.at(-1)!,
            uri = ns[parts.length > 1 ? parts[0]! : ""] || "";
          if (parts.length > 1 && !uri) throw new Invalid("MALFORMED_XML");
          for (const key of Object.keys(attrs)) {
            const prefix = key.slice(2).split(":");
            if (prefix.length > 1 && prefix[0] !== "xmlns" && !ns[prefix[0]!])
              throw new Invalid("MALFORMED_XML");
          }
          const attr = (key: string) =>
            Object.entries(attrs).find(([k]) => {
              const p = k.slice(2).split(":");
              return p.at(-1) === key && (p.length === 1 || ns[p[0]!] === W);
            })?.[1];
          const children = item[name] as Ordered[];
          if (entry.name === "word/document.xml" && frame.depth === 0)
            main = local === "document" && uri === W;
          if (
            entry.name === "[Content_Types].xml" &&
            local === "Override" &&
            attrs["@_PartName"] === "/word/document.xml" &&
            attrs["@_ContentType"] ===
              "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
          )
            types = true;
          if (uri === W) {
            if (revisions.has(local)) {
              add("TRACKED_CHANGES");
              if (
                ["cellIns", "cellDel", "cellMerge"].includes(local) ||
                (["ins", "del"].includes(local) &&
                  [W + "trPr", W + "tcPr", W + "rPr"].includes(
                    frame.parent || "",
                  ))
              )
                add("STRUCTURAL_REVISIONS");
              if (
                ![
                  "ins",
                  "del",
                  "delText",
                  "moveFrom",
                  "moveTo",
                  "moveFromRangeStart",
                  "moveFromRangeEnd",
                  "moveToRangeStart",
                  "moveToRangeEnd",
                ].includes(local)
              )
                originalViewUnsupported = true;
            }
            if (
              [
                "comment",
                "commentRangeStart",
                "commentRangeEnd",
                "commentReference",
              ].includes(local)
            )
              add("COMMENTS");
            if (
              local === "vanish" &&
              !["0", "false", "off"].includes(attr("val") || "")
            )
              add("HIDDEN_TEXT");
            if (
              [
                "embedRegular",
                "embedBold",
                "embedItalic",
                "embedBoldItalic",
              ].includes(local)
            )
              add("EMBEDDED_FONTS");
            if (["object", "altChunk"].includes(local)) add("EMBEDDED_OBJECTS");
            if (local === "rFonts")
              for (const key of ["ascii", "hAnsi", "eastAsia", "cs"]) {
                const font = attr(key);
                if (
                  font &&
                  font.length <= 80 &&
                  ![...font].some((c) => c.charCodeAt(0) < 32) &&
                  fonts.size < 40
                )
                  fonts.add(font);
              }
          }
          if (
            local === "Relationship" &&
            attrs["@_Type"]?.split("/").at(-1) === "font"
          )
            add("EMBEDDED_FONTS");
          if (
            local === "Relationship" &&
            attrs["@_TargetMode"]?.toLowerCase() === "external" &&
            (attrs["@_Type"]?.split("/").at(-1) !== "hyperlink" ||
              !/^(https?:\/\/|mailto:)/i.test(attrs["@_Target"] || ""))
          )
            add("EXTERNAL_CONTENT");
          if (["instrText", "fldSimple"].includes(local)) {
            fields +=
              children.map((c) => String(c["#text"] || "")).join("") +
              (attr("instr") || "");
            warnings.add(
              "Page numbers and contents may be recalculated. Check the resulting contents and links.",
            );
          }
          if (
            ["anchor", "txbxContent", "oMath", "chart", "diagram"].includes(
              local,
            ) ||
            (local === "cols" &&
              attr("num") !== undefined &&
              attr("num") !== "1")
          )
            complexLayout = true;
          for (let i = children.length - 1; i >= 0; i--)
            stack.push({
              items: [children[i]!],
              ns,
              parent: uri + local,
              depth: frame.depth + 1,
            });
        }
      }
      if (
        /\b(DDEAUTO|DDE|INCLUDETEXT|INCLUDEPICTURE|DATABASE|LINK)\b/i.test(
          fields,
        )
      )
        add("EXTERNAL_DATA_FIELDS");
    }
    if (!main || !types) throw new Invalid("INVALID_DOCX");
    if (
      !visible &&
      !list.some((e) => e.name.startsWith("word/media/")) &&
      !codes.size
    )
      add("EMPTY_DOCUMENT");
  } catch (error) {
    add(error instanceof Invalid ? error.code : "INVALID_DOCX");
  }
  if (complexLayout)
    warnings.add(
      "This document contains complex layout. Check pictures, columns and equations in the preview.",
    );
  return {
    issues: [...codes].map((code) => ({
      code,
      message: messages[code] || messages.INVALID_DOCX!,
    })),
    warnings: [...warnings],
    revisions: codes.has("TRACKED_CHANGES"),
    originalViewUnsupported,
    comments: codes.has("COMMENTS"),
    fonts: [...fonts],
    complexLayout,
  };
}
