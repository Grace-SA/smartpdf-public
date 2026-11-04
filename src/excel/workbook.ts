import { Inflate } from "pako";
import { XMLParser, XMLValidator } from "fast-xml-parser";

export type Sheet = { index: number; name: string; hidden: boolean };
export type ExcelOptions = {
  sheets: number[];
  orientation: "keep" | "portrait" | "landscape";
  paper: "keep" | "A4" | "Letter";
  scale: "keep" | "width" | "page";
};
export const defaultOptions = (): ExcelOptions => ({
  sheets: [],
  orientation: "keep",
  paper: "keep",
  scale: "keep",
});

/** Metadata only. Server independently validates the complete uploaded package. */
export function readSheets(bytes: Uint8Array): Sheet[] {
  const fail = () => {
    throw new Error(
      "Choose a valid, unencrypted XLSX workbook with up to 50 worksheets.",
    );
  };
  if (bytes.length < 22 || bytes.length > 30 * 1024 ** 2) return fail();
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let end = bytes.length - 22;
  for (; end >= Math.max(0, bytes.length - 65557); end--) {
    if (
      view.getUint32(end, true) === 0x06054b50 &&
      end + 22 + view.getUint16(end + 20, true) === bytes.length
    )
      break;
  }
  if (end < 0 || view.getUint16(end + 4, true) || view.getUint16(end + 6, true))
    return fail();
  const count = view.getUint16(end + 10, true);
  if (!count || count > 2048 || count !== view.getUint16(end + 8, true))
    return fail();
  let offset = view.getUint32(end + 16, true);
  const directoryEnd = offset + view.getUint32(end + 12, true);
  if (directoryEnd !== end) return fail();
  let xml: Uint8Array | undefined;
  const names = new Set<string>();
  for (let i = 0; i < count; i++) {
    if (offset + 46 > end || view.getUint32(offset, true) !== 0x02014b50)
      return fail();
    const length = view.getUint16(offset + 28, true);
    const next =
      offset +
      46 +
      length +
      view.getUint16(offset + 30, true) +
      view.getUint16(offset + 32, true);
    if (next > end) return fail();
    const name = new TextDecoder().decode(
      bytes.subarray(offset + 46, offset + 46 + length),
    );
    if (names.has(name)) return fail();
    names.add(name);
    if (name === "xl/workbook.xml") {
      const method = view.getUint16(offset + 10, true);
      const compressed = view.getUint32(offset + 20, true);
      const size = view.getUint32(offset + 24, true);
      const local = view.getUint32(offset + 42, true);
      if (
        view.getUint16(offset + 8, true) & 1 ||
        size > 1024 * 1024 ||
        local + 30 > end ||
        view.getUint32(local, true) !== 0x04034b50
      )
        return fail();
      const begin =
        local +
        30 +
        view.getUint16(local + 26, true) +
        view.getUint16(local + 28, true);
      if (begin + compressed > end) return fail();
      const input = bytes.subarray(begin, begin + compressed);
      if (method === 0) xml = input.slice();
      else if (method === 8) {
        const inflate = new Inflate({ raw: true, chunkSize: 16384 });
        const chunks: Uint8Array[] = [];
        let decoded = 0;
        inflate.onData = (chunk) => {
          decoded += chunk.length;
          if (decoded > 1024 * 1024 || decoded > size) fail();
          chunks.push(chunk);
        };
        inflate.push(input, true);
        if (inflate.err || !inflate.ended) return fail();
        xml = new Uint8Array(decoded);
        let at = 0;
        for (const chunk of chunks) {
          xml.set(chunk, at);
          at += chunk.length;
        }
      } else return fail();
      if (xml.length !== size) return fail();
    }
    offset = next;
  }
  if (offset !== end || !xml) return fail();
  const text = new TextDecoder("utf-8", { fatal: true }).decode(xml);
  if (
    /<!\s*(?:DOCTYPE|ENTITY)/i.test(text) ||
    XMLValidator.validate(text) !== true
  )
    return fail();
  const parsed = new XMLParser({
    ignoreAttributes: false,
    attributeNamePrefix: "",
    removeNSPrefix: true,
    processEntities: true,
    parseTagValue: false,
  }).parse(text);
  const items = parsed?.workbook?.sheets?.sheet;
  const list = Array.isArray(items) ? items : items ? [items] : [];
  if (!list.length || list.length > 50) return fail();
  return list.map((item, index) => {
    if (
      typeof item.name !== "string" ||
      !item.name ||
      item.name.length > 255 ||
      ![undefined, "visible", "hidden", "veryHidden"].includes(item.state)
    )
      return fail();
    return {
      index,
      name: item.name,
      hidden: item.state === "hidden" || item.state === "veryHidden",
    };
  });
}
