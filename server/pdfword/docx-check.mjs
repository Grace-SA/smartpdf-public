import { readFile } from "node:fs/promises";
import { inflateRawSync, inflateSync, crc32 } from "node:zlib";
import { XMLValidator, XMLParser } from "fast-xml-parser";
import path from "node:path";

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
    count > 1024 ||
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
    if (/^word\/media\/image\d+\.png$/.test(name)) {
      if (
        value.length < 45 ||
        !value.subarray(0, 8).equals(Buffer.from("89504e470d0a1a0a", "hex"))
      )
        fail();
      const pixels = [];
      let scanlineBytes = 0;
      let position = 8,
        ended = false,
        chunks = 0;
      while (position + 12 <= value.length) {
        const length = value.readUInt32BE(position);
        const type = value.toString("ascii", position + 4, position + 8);
        if (length > value.length - position - 12 || ++chunks > 4096) fail();
        if (
          crc32(value.subarray(position + 4, position + 8 + length)) !==
          value.readUInt32BE(position + 8 + length)
        )
          fail();
        if (chunks === 1) {
          if (type !== "IHDR" || length !== 13) fail();
          const width = value.readUInt32BE(position + 8),
            height = value.readUInt32BE(position + 12);
          if (!width || !height || width * height > 16000000) fail();
          const depth = value[position + 16],
            color = value[position + 17];
          if (
            depth !== 8 ||
            ![2, 6].includes(color) ||
            value[position + 18] ||
            value[position + 19] ||
            value[position + 20]
          )
            fail();
          scanlineBytes = (1 + width * (color === 2 ? 3 : 4)) * height;
        }
        if (type === "IDAT")
          pixels.push(value.subarray(position + 8, position + 8 + length));
        if (!["IHDR", "IDAT", "IEND"].includes(type)) fail();
        position += length + 12;
        if (type === "IEND") {
          ended = true;
          break;
        }
      }
      if (!ended || position !== value.length) fail();
      if (
        !pixels.length ||
        inflateSync(Buffer.concat(pixels), { maxOutputLength: scanlineBytes })
          .length !== scanlineBytes
      )
        fail();
      entries.set(name, null);
      offset += 46 + nameSize + extra + comment;
      localEnd = data + packed;
      continue;
    }
    if (!name.endsWith(".xml") && !name.endsWith(".rels")) fail();
    const xml = value.toString("utf8");
    if (/<!DOCTYPE|<!ENTITY/i.test(xml) || XMLValidator.validate(xml) !== true)
      fail();
    if (
      name.endsWith(".rels") &&
      /TargetMode\s*=\s*["']External["']/i.test(xml)
    )
      fail();
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
  const parser = new XMLParser({ ignoreAttributes: false });
  const relationships = new Map();
  const allowed =
    /\/(officeDocument|core-properties|extended-properties|styles|stylesWithEffects|settings|webSettings|fontTable|theme|numbering|header|footer|image|customXml|customXmlProps)$/;
  for (const [name, xml] of entries) {
    if (!name.endsWith(".rels")) continue;
    const source =
      name === "_rels/.rels" ? "" : name.replace(/_rels\/([^/]+)\.rels$/, "$1");
    const parsed = parser.parse(xml)?.Relationships?.Relationship;
    const links = parsed ? (Array.isArray(parsed) ? parsed : [parsed]) : [];
    const ids = new Map();
    for (const link of links) {
      const target = link["@_Target"],
        id = link["@_Id"];
      if (
        !id ||
        ids.has(id) ||
        typeof target !== "string" ||
        /[\\\\:#?%]/.test(target) ||
        target.startsWith("/") ||
        link["@_TargetMode"] ||
        !allowed.test(link["@_Type"] || "")
      )
        fail();
      const resolved = path.posix.normalize(
        path.posix.join(path.posix.dirname(source), target),
      );
      if (resolved.startsWith("../") || !entries.has(resolved)) fail();
      ids.set(id, resolved);
    }
    relationships.set(source, ids);
  }
  if (
    ![...(relationships.get("")?.values() || [])].includes("word/document.xml")
  )
    fail();
  let images = 0;
  for (const [name, xml] of entries) {
    if (!xml || name.endsWith(".rels")) continue;
    if (/<(?:w:altChunk|w:object|o:OLEObject|w:instrText)\b/.test(xml)) fail();
    for (const match of xml.matchAll(/\br:(?:embed|id)="([^"]+)"/g)) {
      if (!relationships.get(name)?.has(match[1])) fail();
    }
    images += [...xml.matchAll(/<a:blip\b/g)].length;
  }
  const document = parser.parse(entries.get("word/document.xml"));
  if (
    !document["w:document"]?.["w:body"] ||
    !/<(?:w|m):t(?:\s[^>]*)?>[^<]+<\/(?:w|m):t>/.test(
      entries.get("word/document.xml"),
    )
  )
    fail();
  const body = entries.get("word/document.xml");
  const markers = [...body.matchAll(/w:name="smartpdf_page_(\d+)"/g)].map((m) =>
    Number(m[1]),
  );
  if (markers.length && markers.some((n, i) => n !== i + 1)) fail();
  return {
    pages: markers.length || 1,
    sourceMarkers: markers.length,
    images,
    tables: [...body.matchAll(/<w:tbl[ >]/g)].length,
  };
}
