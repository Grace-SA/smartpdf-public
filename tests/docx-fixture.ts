import { deflateRawSync } from "node:zlib";
import { crc32 } from "../src/word/preflight-core";
/** Reviewed synthetic OOXML, generated in memory; never private corpus data. */
export function docxFixture(
  body = "<w:p><w:r><w:t>Synthetic report</w:t></w:r></w:p>",
  extra: Record<string, string> = {},
  compressed = true,
): Buffer {
  const files = {
    "[Content_Types].xml":
      '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
    "word/document.xml":
      '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' +
      body +
      "</w:body></w:document>",
    ...extra,
  };
  const parts: Buffer[] = [],
    central: Buffer[] = [];
  let offset = 0;
  for (const [name, text] of Object.entries(files)) {
    const raw = Buffer.from(text),
      data = compressed ? deflateRawSync(raw) : raw,
      encoded = Buffer.from(name),
      crc = crc32(raw);
    const l = Buffer.alloc(30 + encoded.length);
    l.writeUInt32LE(0x04034b50);
    l.writeUInt16LE(20, 4);
    l.writeUInt16LE(0x800, 6);
    l.writeUInt16LE(compressed ? 8 : 0, 8);
    l.writeUInt32LE(crc, 14);
    l.writeUInt32LE(data.length, 18);
    l.writeUInt32LE(raw.length, 22);
    l.writeUInt16LE(encoded.length, 26);
    encoded.copy(l, 30);
    const c = Buffer.alloc(46 + encoded.length);
    c.writeUInt32LE(0x02014b50);
    c.writeUInt16LE(20, 4);
    c.writeUInt16LE(20, 6);
    c.writeUInt16LE(0x800, 8);
    c.writeUInt16LE(compressed ? 8 : 0, 10);
    c.writeUInt32LE(crc, 16);
    c.writeUInt32LE(data.length, 20);
    c.writeUInt32LE(raw.length, 24);
    c.writeUInt16LE(encoded.length, 28);
    c.writeUInt32LE(offset, 42);
    encoded.copy(c, 46);
    parts.push(l, data);
    central.push(c);
    offset += l.length + data.length;
  }
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50);
  end.writeUInt16LE(central.length, 8);
  end.writeUInt16LE(central.length, 10);
  end.writeUInt32LE(
    central.reduce((n, c) => n + c.length, 0),
    12,
  );
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...parts, ...central, end]);
}
