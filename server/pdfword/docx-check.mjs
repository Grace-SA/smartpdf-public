import { readFile } from "node:fs/promises";
import { inflateRawSync, crc32 } from "node:zlib";
import { XMLValidator, XMLParser } from "fast-xml-parser";

// Independent OPC validation: neither PDFium nor the Word writer is used here.
export async function checkDocx(file) {
  const bytes = await readFile(file);
  const fail = () => {
    throw Error("Invalid Word output");
  };
  if (bytes.length < 22 || bytes.length > 30 * 1024 ** 2) fail();
  const end = bytes.length - 22;
  if (bytes.readUInt32LE(end) !== 0x06054b50 || bytes.readUInt16LE(end + 20))
    fail();
  if (bytes.readUInt16LE(end + 4) || bytes.readUInt16LE(end + 6)) fail();
  const count = bytes.readUInt16LE(end + 10);
  const size = bytes.readUInt32LE(end + 12);
  const start = bytes.readUInt32LE(end + 16);
  if (
    !count ||
    count > 128 ||
    start + size !== end ||
    bytes.readUInt16LE(end + 8) !== count
  )
    fail();
  let offset = start,
    expanded = 0,
    localEnd = 0;
  const entries = new Map();
  for (let i = 0; i < count; i++) {
    if (offset + 46 > end || bytes.readUInt32LE(offset) !== 0x02014b50) fail();
    const flags = bytes.readUInt16LE(offset + 8),
      method = bytes.readUInt16LE(offset + 10);
    const crc = bytes.readUInt32LE(offset + 16),
      packed = bytes.readUInt32LE(offset + 20);
    const unpacked = bytes.readUInt32LE(offset + 24),
      nameSize = bytes.readUInt16LE(offset + 28);
    const extra = bytes.readUInt16LE(offset + 30),
      comment = bytes.readUInt16LE(offset + 32);
    const local = bytes.readUInt32LE(offset + 42);
    if (
      flags & ~0x800 ||
      ![0, 8].includes(method) ||
      unpacked > 8 * 1024 ** 2 ||
      offset + 46 + nameSize + extra + comment > end
    )
      fail();
    const name = bytes
      .subarray(offset + 46, offset + 46 + nameSize)
      .toString("utf8");
    if (
      !/^[\w[\]./-]+$/.test(name) ||
      name.startsWith("/") ||
      name.split("/").includes("..") ||
      entries.has(name)
    )
      fail();
    if (
      local !== localEnd ||
      local + 30 > start ||
      bytes.readUInt32LE(local) !== 0x04034b50
    )
      fail();
    const localName = bytes.readUInt16LE(local + 26),
      localExtra = bytes.readUInt16LE(local + 28);
    const data = local + 30 + localName + localExtra;
    if (
      data + packed > start ||
      bytes.subarray(local + 30, local + 30 + localName).toString("utf8") !==
        name ||
      bytes.readUInt16LE(local + 6) !== flags ||
      bytes.readUInt16LE(local + 8) !== method ||
      bytes.readUInt32LE(local + 14) !== crc ||
      bytes.readUInt32LE(local + 18) !== packed ||
      bytes.readUInt32LE(local + 22) !== unpacked
    )
      fail();
    expanded += unpacked;
    if (expanded > 32 * 1024 ** 2) fail();
    const compressed = bytes.subarray(data, data + packed);
    const value =
      method === 8
        ? inflateRawSync(compressed, { maxOutputLength: 8 * 1024 ** 2 })
        : compressed;
    if (value.length !== unpacked || crc32(value) !== crc) fail();
    // This milestone exports text only, so every part must be XML.
    if (!name.endsWith(".xml") && !name.endsWith(".rels")) fail();
    const xml = value.toString("utf8");
    if (/<!DOCTYPE|<!ENTITY/i.test(xml) || XMLValidator.validate(xml) !== true)
      fail();
    if (name.endsWith(".rels")) {
      // Inspect decoded XML attributes, not source spelling: character
      // references such as Extern&#97;l have the same OPC meaning as External.
      const relationships = new XMLParser({
        ignoreAttributes: false,
        removeNSPrefix: true,
        isArray: (tag) => tag === "Relationship",
      }).parse(xml).Relationships;
      if (!relationships) fail();
      for (const relationship of relationships.Relationship || []) {
        const mode = relationship["@_TargetMode"];
        const target = relationship["@_Target"];
        if (
          (mode !== undefined && mode !== "Internal") ||
          typeof target !== "string" ||
          /^[a-z][a-z0-9+.-]*:|^\/\//i.test(target)
        )
          fail();
      }
    }
    entries.set(name, xml);
    offset += 46 + nameSize + extra + comment;
    localEnd = data + packed;
  }
  if (offset !== end || localEnd !== start) fail();
  const content = entries.get("[Content_Types].xml") || "";
  if (
    !content.includes(
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
    ) ||
    /macroEnabled|vbaProject/i.test(content)
  )
    fail();
  if (!entries.has("_rels/.rels") || !entries.has("word/document.xml")) fail();
  const document = new XMLParser({ ignoreAttributes: false }).parse(
    entries.get("word/document.xml"),
  );
  if (
    !document["w:document"]?.["w:body"] ||
    !/<w:t(?:\s[^>]*)?>[^<]+<\/w:t>/.test(entries.get("word/document.xml"))
  )
    fail();
  return { pages: 1 };
}
