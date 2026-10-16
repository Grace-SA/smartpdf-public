import { PDFContext, PDFRawStream, decodePDFRawStream } from "pdf-lib";
import { LIMITS, ProbeFailure } from "./contracts";

const tokenDecoder = new TextDecoder();
const spaces = new Uint8Array(256),
  separators = new Uint8Array(256);
for (const b of [0, 9, 10, 12, 13, 32]) spaces[b] = separators[b] = 1;
for (const b of [40, 41, 60, 62, 91, 93, 123, 125, 47, 37]) separators[b] = 1;

// Content-stream lexer, not a search over raw PDF bytes. Literal/hex strings,
// names, arrays and comments must not be mistaken for inline-image operators.
export function inspectInlineImages(
  bytes: Uint8Array,
  remainingWork: number = LIMITS.streamedImageWorkBytes,
  onMcid?: () => void,
): number {
  let at = 0,
    work = 0;
  const whitespace = (b: number) => spaces[b] === 1;
  const delimiter = (b: number) => separators[b] === 1;
  const unsupported = (): never => {
    throw new ProbeFailure("UNSUPPORTED_PDF", "inlineImage");
  };
  function boundedDecode(raw: PDFRawStream) {
    try {
      const decoder = decodePDFRawStream(raw);
      return { decoder, raster: decoder.decode() };
    } catch (error) {
      if (
        error instanceof Error &&
        error.message === "SMARTWORKS_RESOURCE_LIMIT"
      )
        throw new ProbeFailure("RESOURCE_LIMIT", "complexity");
      return unsupported();
    }
  }
  function token(full = true): string | undefined {
    while (at < bytes.length) {
      if (whitespace(bytes[at]!)) {
        at++;
        continue;
      }
      if (bytes[at] === 37) {
        while (at < bytes.length && ![10, 13].includes(bytes[at]!)) at++;
        continue;
      }
      break;
    }
    if (at >= bytes.length) return undefined;
    const start = at++;
    if (bytes[start] === 40) {
      let depth = 1;
      while (at < bytes.length && depth) {
        const b = bytes[at++]!;
        if (b === 92) at++;
        else if (b === 40) depth++;
        else if (b === 41) depth--;
      }
      return "string";
    }
    if (bytes[start] === 60 && bytes[at] !== 60) {
      while (at < bytes.length && bytes[at++] !== 62) {
        /* hex string */
      }
      return "string";
    }
    if ([60, 62].includes(bytes[start]!) && bytes[at] === bytes[start]) {
      at++;
      return bytes[start] === 60 ? "<<" : ">>";
    }
    if ([91, 93].includes(bytes[start]!))
      return String.fromCharCode(bytes[start]!);
    while (at < bytes.length && !delimiter(bytes[at]!)) at++;
    // Outside BI headers only BI and /MCID matter. Still lex every byte,
    // string, comment and container, but do not allocate text for coordinates
    // and ordinary drawing operators. Inline headers keep exact token values.
    if (!full && !(bytes[start] === 47 && onMcid))
      return at - start === 2 && bytes[start] === 66 && bytes[start + 1] === 73
        ? "BI"
        : "";
    const result = tokenDecoder.decode(bytes.subarray(start, at));
    if (
      onMcid &&
      result.startsWith("/") &&
      result.replace(/#([0-9a-f]{2})/gi, (_, h: string) =>
        String.fromCharCode(parseInt(h, 16)),
      ) === "/MCID"
    )
      onMcid?.();
    return result;
  }
  let nesting = 0;
  for (let value = token(false); value !== undefined; value = token(false)) {
    if (value === "[" || value === "<<") {
      nesting++;
      continue;
    }
    if (value === "]" || value === ">>") {
      nesting--;
      continue;
    }
    if (value !== "BI" || nesting !== 0) continue;
    type Value = string | string[] | Record<string, string>;
    const header: Record<string, Value> = {};
    const decodedName = (v: string) =>
      v.replace(/#([0-9a-f]{2})/gi, (_, h: string) =>
        String.fromCharCode(parseInt(h, 16)),
      );
    function headerValue(): Value {
      const v = token();
      if (!v) return unsupported();
      if (v === "[") {
        const a: string[] = [];
        for (let x = token(); x !== "]"; x = token()) {
          if (!x || ["[", "<<", "ID"].includes(x) || a.length >= 16)
            unsupported();
          a.push(decodedName(x!));
        }
        return a;
      }
      if (v === "<<") {
        const d: Record<string, string> = {};
        for (let k = token(); k !== ">>"; k = token()) {
          if (!k?.startsWith("/") || Object.keys(d).length >= 8) unsupported();
          const x = token();
          if (!x || !Number.isFinite(Number(x))) unsupported();
          d[decodedName(k!)] = x!;
        }
        return d;
      }
      return decodedName(v);
    }
    let field = token();
    while (field !== "ID") {
      if (!field?.startsWith("/")) unsupported();
      const key = decodedName(field!);
      if (header[key] !== undefined) unsupported();
      header[key] = headerValue();
      if (Object.keys(header).length > 16) unsupported();
      field = token();
    }
    const get = (short: string, long: string) => header[short] ?? header[long];
    const width = Number(get("/W", "/Width")),
      height = Number(get("/H", "/Height"));
    if (![width, height].every((n) => Number.isSafeInteger(n) && n > 0))
      unsupported();
    if (width * height > LIMITS.imagePixels)
      throw new ProbeFailure("RESOURCE_LIMIT", "image");
    const mask = get("/IM", "/ImageMask");
    if (mask !== undefined && mask !== "true" && mask !== "false")
      unsupported();
    const bits = Number(
      get("/BPC", "/BitsPerComponent") ?? (mask === "true" ? 1 : NaN),
    );
    if (![1, 2, 4, 8, 16].includes(bits) || (mask === "true" && bits !== 1))
      unsupported();
    const color = get("/CS", "/ColorSpace");
    const channels =
      mask === "true"
        ? 1
        : ["/RGB", "/DeviceRGB"].includes(String(color))
          ? 3
          : ["/G", "/DeviceGray"].includes(String(color))
            ? 1
            : ["/CMYK", "/DeviceCMYK"].includes(String(color))
              ? 4
              : 0;
    if (!whitespace(bytes[at]!)) unsupported();
    if (bytes[at++] === 13 && bytes[at] === 10) at++;
    const rawFilter = get("/F", "/Filter");
    if (!rawFilter) {
      if (!channels) unsupported();
      at += Math.ceil((width * channels * bits) / 8) * height;
    } else {
      const fs =
        typeof rawFilter === "string"
          ? [rawFilter]
          : Array.isArray(rawFilter)
            ? rawFilter
            : unsupported();
      const filters = fs.map((f) =>
        f === "/Fl" ? "/FlateDecode" : f === "/A85" ? "/ASCII85Decode" : f,
      );
      if (
        !(filters.length === 1 && filters[0] === "/FlateDecode") &&
        !(
          filters.length === 2 &&
          filters[0] === "/ASCII85Decode" &&
          filters[1] === "/FlateDecode"
        )
      )
        unsupported();
      let encoded = bytes.subarray(at),
        extent: number | undefined;
      if (filters.length === 2) {
        let end = at;
        while (
          end + 1 < bytes.length &&
          !(bytes[end] === 126 && bytes[end + 1] === 62)
        )
          end++;
        if (end + 1 >= bytes.length) unsupported();
        extent = end + 2 - at;
        const c = PDFContext.create();
        encoded = boundedDecode(
          PDFRawStream.of(
            c.obj({ Subtype: "Image", Filter: "ASCII85Decode" }),
            bytes.subarray(at, end + 2),
          ),
        ).raster;
      }
      const c = PDFContext.create();
      const { decoder, raster } = boundedDecode(
        PDFRawStream.of(
          c.obj({ Subtype: "Image", Filter: "FlateDecode" }),
          encoded,
        ),
      );
      work += raster.length;
      if (work > remainingWork)
        throw new ProbeFailure("RESOURCE_LIMIT", "complexity");
      // Pinned pdf-lib inflater exposes the consumed input position and unread
      // lookahead bits. Read the zlib checksum at the exact compressed endpoint;
      // never search for an EI token inside binary image data.
      const state = decoder as unknown as {
        stream: { pos: number };
        codeSize: number;
      };
      const end = state.stream.pos - Math.floor(state.codeSize / 8);
      if (end + 4 > encoded.length) unsupported();
      let a = 1,
        b = 0;
      for (const octet of raster) {
        a = (a + octet) % 65521;
        b = (b + a) % 65521;
      }
      const checksum = new DataView(
        encoded.buffer,
        encoded.byteOffset + end,
        4,
      ).getUint32(0);
      if (
        ((b << 16) | a) >>> 0 !== checksum ||
        (extent !== undefined && end + 4 !== encoded.length)
      )
        unsupported();
      const rawParams = get("/DP", "/DecodeParms");
      const params =
        rawParams && typeof rawParams === "object" && !Array.isArray(rawParams)
          ? rawParams
          : {};
      if (rawParams && params !== rawParams) unsupported();
      if (
        Object.keys(params).some(
          (k) =>
            ![
              "/Predictor",
              "/Colors",
              "/BitsPerComponent",
              "/Columns",
            ].includes(k),
        )
      )
        unsupported();
      const predictor = Number(params["/Predictor"] ?? 1),
        components = Number(params["/Colors"] ?? 1);
      const columns = Number(params["/Columns"] ?? width),
        sampleBits = Number(params["/BitsPerComponent"] ?? 8);
      if (![1, 2, 10, 11, 12, 13, 14, 15].includes(predictor)) unsupported();
      if (
        predictor !== 1 &&
        (!Number.isSafeInteger(components) ||
          components < 1 ||
          components > 4 ||
          columns !== width ||
          sampleBits !== bits)
      )
        unsupported();
      const rowBytes = Math.ceil(
        (width *
          (predictor === 1 ? channels || components : components) *
          bits) /
          8,
      );
      if (raster.length !== (rowBytes + (predictor >= 10 ? 1 : 0)) * height)
        unsupported();
      at += extent ?? end + 4;
    }
    if (at >= bytes.length || !whitespace(bytes[at]!) || token() !== "EI")
      unsupported();
  }
  return work;
}
