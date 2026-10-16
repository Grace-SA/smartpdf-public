import { PHOTO_LIMITS, photoCopy } from "./model";
import { heicColor, type PhotoColor } from "./heic-color";
import { isHeic } from "./heic-header";
type Box = { kind: string; start: number; end: number };
export type HeicInfo = { color?: PhotoColor; hdrGainMap: boolean };
export function inspectHeic(bytes: Uint8Array): HeicInfo {
  if (bytes.length > PHOTO_LIMITS.fileBytes) throw new Error(photoCopy.large);
  if (!isHeic(bytes)) throw new Error("This is not a complete HEIC image.");
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const invalid = () => new Error("Incomplete or ambiguous HEIC structure.");
  const text = (p: number) => String.fromCharCode(...bytes.subarray(p, p + 4));
  let count = 0;
  function boxes(start: number, end: number): Box[] {
    const result: Box[] = [];
    for (let p = start; p < end;) {
      if (++count > 10000 || p + 8 > end) throw invalid();
      let size = view.getUint32(p),
        header = 8;
      if (size === 1) {
        if (p + 16 > end) throw invalid();
        const big = view.getBigUint64(p + 8);
        if (big > BigInt(end - p)) throw invalid();
        size = Number(big);
        header = 16;
      } else if (size === 0) size = end - p;
      if (size < header || p + size > end) throw invalid();
      result.push({ kind: text(p + 4), start: p + header, end: p + size });
      p += size;
    }
    return result;
  }
  const top = boxes(0, bytes.length);
  if (top.some((b) => b.kind === "moov"))
    throw new Error(
      "HEIC image sequences are not supported. Export individual still photos first.",
    );
  const one = (items: Box[], kind: string) => {
    const found = items.filter((b) => b.kind === kind);
    if (found.length !== 1) throw invalid();
    return found[0]!;
  };
  const meta = one(top, "meta");
  if (meta.start + 4 > meta.end || view.getUint32(meta.start) !== 0)
    throw invalid();
  const children = boxes(meta.start + 4, meta.end),
    pitm = one(children, "pitm");
  const version = bytes[pitm.start];
  if (
    (version !== 0 && version !== 1) ||
    pitm.start + (version === 0 ? 6 : 8) !== pitm.end
  )
    throw invalid();
  const primary =
    version === 0
      ? view.getUint16(pitm.start + 4)
      : view.getUint32(pitm.start + 4);
  const iprp = one(children, "iprp"),
    propertyBoxes = boxes(iprp.start, iprp.end),
    ipco = one(propertyBoxes, "ipco");
  const properties = boxes(ipco.start, ipco.end);
  let dimensions = 0;
  for (const property of properties)
    if (property.kind === "ispe") {
      if (property.end - property.start !== 12) throw invalid();
      const w = view.getUint32(property.start + 4),
        h = view.getUint32(property.start + 8);
      if (!w || !h || w * h > PHOTO_LIMITS.pixels)
        throw new Error(photoCopy.large);
      dimensions++;
    }
  if (!dimensions) throw invalid();
  const associations = new Map<number, number[]>();
  for (const box of propertyBoxes.filter((b) => b.kind === "ipma")) {
    if (box.start + 8 > box.end) throw invalid();
    const v = bytes[box.start]!,
      flags = view.getUint32(box.start) & 0xffffff;
    if (v > 1 || flags > 1) throw invalid();
    const entries = view.getUint32(box.start + 4);
    if (entries > 10000) throw invalid();
    let p = box.start + 8;
    for (let i = 0; i < entries; i++) {
      const idBytes = v === 0 ? 2 : 4;
      if (p + idBytes + 1 > box.end) throw invalid();
      const id = idBytes === 2 ? view.getUint16(p) : view.getUint32(p);
      p += idBytes;
      const n = bytes[p++]!,
        indices: number[] = [];
      for (let j = 0; j < n; j++) {
        const size = flags & 1 ? 2 : 1;
        if (p + size > box.end) throw invalid();
        const index =
          (size === 2 ? view.getUint16(p) : bytes[p]!) &
          (size === 2 ? 0x7fff : 0x7f);
        p += size;
        if (index > properties.length) throw invalid();
        if (index) indices.push(index - 1);
      }
      if (associations.has(id)) throw invalid();
      associations.set(id, indices);
    }
    if (p !== box.end) throw invalid();
  }
  const primaryIndices = associations.get(primary);
  if (!primaryIndices) throw invalid();
  // Auxiliary images have independent color metadata; use only the primary.
  const profiles = primaryIndices
    .map((i) => properties[i]!)
    .filter((b) => b.kind === "colr");
  let profile: Uint8Array | undefined;
  for (const b of profiles) {
    const next = bytes.subarray(b.start, b.end),
      kind = text(b.start);
    if (
      kind === "nclx" &&
      next.length >= 11 &&
      [16, 18].includes(view.getUint16(b.start + 6))
    )
      throw new Error(
        "This HEIC has an HDR-only primary image. Export an SDR JPEG first.",
      );
    if (
      profile &&
      String.fromCharCode(...profile.subarray(0, 4)) === kind &&
      (profile.length !== next.length || profile.some((v, i) => v !== next[i]))
    )
      throw invalid();
    if (!profile || kind !== "nclx") profile = next;
  }
  const auxiliaryTargets = new Map<number, number[]>();
  for (const box of children.filter((b) => b.kind === "iref")) {
    if (box.start + 4 > box.end || bytes[box.start]! > 1) throw invalid();
    const idBytes = bytes[box.start] === 0 ? 2 : 4;
    for (const ref of boxes(box.start + 4, box.end)) {
      if (ref.kind !== "auxl") continue;
      let p = ref.start;
      if (p + idBytes + 2 > ref.end) throw invalid();
      const readId = () => {
        if (p + idBytes > ref.end) throw invalid();
        const id = idBytes === 2 ? view.getUint16(p) : view.getUint32(p);
        p += idBytes;
        return id;
      };
      const from = readId(),
        n = view.getUint16(p);
      p += 2;
      if (n * idBytes !== ref.end - p) throw invalid();
      const targets = Array.from({ length: n }, readId);
      if (auxiliaryTargets.has(from)) throw invalid();
      auxiliaryTargets.set(from, targets);
    }
  }
  let hdrGainMap = false;
  for (const [id, indices] of associations)
    for (const index of indices) {
      const property = properties[index]!;
      if (property.kind !== "auxC") continue;
      if (property.start + 5 > property.end) throw invalid();
      const type = new TextDecoder()
        .decode(bytes.subarray(property.start + 4, property.end))
        .replace(/\0.*$/s, "");
      if (!/gainmap|hdr/i.test(type)) continue;
      if (
        type !== "urn:com:apple:photo:2020:aux:hdrgainmap" ||
        !auxiliaryTargets.get(id)?.includes(primary)
      )
        throw new Error(
          "This HEIC HDR structure is not supported. Export an SDR JPEG first.",
        );
      hdrGainMap = true;
    }
  if (hdrGainMap && !profile)
    throw new Error(
      "The HDR photo's base color profile could not be checked. Export an SDR JPEG first.",
    );
  return { color: profile ? heicColor(profile) : undefined, hdrGainMap };
}
