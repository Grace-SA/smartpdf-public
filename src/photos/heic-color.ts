// Matrix/TRC RGB profiles are converted to sRGB before JPEG encoding.
// LUT profiles and HDR need a different pipeline; never discard them silently.
export type PhotoColor = { matrix: number[]; curves: number[][] };
const srgb = (v: number) =>
  v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
const curve = (fn: (v: number) => number) =>
  Array.from({ length: 256 }, (_, i) => fn(i / 255));
const unsupported = () =>
  new Error(
    "This HEIC color profile is not supported. Export an sRGB JPEG first.",
  );
export function heicColor(bytes: Uint8Array): PhotoColor | undefined {
  const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const text = (p: number) => String.fromCharCode(...bytes.subarray(p, p + 4));
  if (text(0) === "nclx") {
    if (bytes.length < 11) throw unsupported();
    const primaries = v.getUint16(4),
      transfer = v.getUint16(6);
    if (![1, 2, 12].includes(primaries) || ![1, 2, 6, 13].includes(transfer))
      throw unsupported();
    if ([1, 2].includes(primaries) && [2, 13].includes(transfer)) return;
    const trc = curve(
      [2, 13].includes(transfer)
        ? srgb
        : (x) => (x < 0.081 ? x / 4.5 : ((x + 0.099) / 1.099) ** (1 / 0.45)),
    );
    return {
      matrix:
        primaries === 12
          ? [
              1.224745, -0.224904, 0, -0.042058, 1.042081, 0, -0.019642,
              -0.078655, 1.098537,
            ]
          : [1, 0, 0, 0, 1, 0, 0, 0, 1],
      curves: [trc, trc, trc],
    };
  }
  if (!["prof", "rICC"].includes(text(0)) || bytes.length < 136)
    throw unsupported();
  const base = 4;
  if (text(base + 16) !== "RGB " || text(base + 20) !== "XYZ ")
    throw unsupported();
  const count = v.getUint32(base + 128);
  if (count > 256 || base + 132 + count * 12 > bytes.length)
    throw unsupported();
  const tags = new Map<string, [number, number]>();
  for (let i = 0; i < count; i++) {
    const p = base + 132 + i * 12,
      start = base + v.getUint32(p + 4),
      length = v.getUint32(p + 8);
    if (start < base || start + length > bytes.length) throw unsupported();
    tags.set(text(p), [start, length]);
  }
  if (["A2B0", "A2B1", "A2B2"].some((key) => tags.has(key)))
    throw unsupported();
  const fixed = (p: number) => v.getInt32(p) / 65536;
  const xyz = ["rXYZ", "gXYZ", "bXYZ"].map((key) => {
    const tag = tags.get(key);
    if (!tag || tag[1] < 20 || text(tag[0]) !== "XYZ ") throw unsupported();
    return [fixed(tag[0] + 8), fixed(tag[0] + 12), fixed(tag[0] + 16)];
  });
  const curves = ["rTRC", "gTRC", "bTRC"].map((key) => {
    const tag = tags.get(key);
    if (!tag || tag[1] < 12) throw unsupported();
    const [p, length] = tag;
    if (text(p) === "curv") {
      const n = v.getUint32(p + 8);
      if (n > 4096 || 12 + n * 2 > length) throw unsupported();
      if (!n) return curve((x) => x);
      if (n === 1) return curve((x) => x ** (v.getUint16(p + 12) / 256));
      return curve((x) => {
        const pos = x * (n - 1),
          low = Math.floor(pos),
          high = Math.min(n - 1, low + 1);
        return (
          (v.getUint16(p + 12 + low * 2) * (high === low ? 1 : high - pos) +
            (high === low ? 0 : v.getUint16(p + 12 + high * 2) * (pos - low))) /
          65535
        );
      });
    }
    if (text(p) !== "para") throw unsupported();
    const kind = v.getUint16(p + 8),
      counts = [1, 3, 4, 5, 7];
    if (kind > 4 || 12 + counts[kind]! * 4 > length) throw unsupported();
    const [g, a = 1, b = 0, c = 0, d = 0, e = 0, f = 0] = Array.from(
      { length: counts[kind]! },
      (_, i) => fixed(p + 12 + i * 4),
    );
    return curve((x) =>
      kind === 0
        ? x ** g!
        : kind === 1
          ? x >= -b / a
            ? (a * x + b) ** g!
            : 0
          : kind === 2
            ? x >= -b / a
              ? (a * x + b) ** g! + c
              : c
            : kind === 3
              ? x >= d
                ? (a * x + b) ** g!
                : c * x
              : x >= d
                ? (a * x + b) ** g! + e
                : c * x + f,
    );
  });
  // ICC PCS is D50; this matrix includes Bradford adaptation to D65.
  const xyzToSrgb = [
    3.1338561, -1.6168667, -0.4906146, -0.9787684, 1.9161415, 0.033454,
    0.0719453, -0.2289914, 1.4052427,
  ];
  const matrix = Array.from({ length: 9 }, (_, i) =>
    xyz[i % 3]!.reduce(
      (sum, val, j) => sum + val * xyzToSrgb[Math.floor(i / 3) * 3 + j]!,
      0,
    ),
  );
  if ([...matrix, ...curves.flat()].some((x) => !Number.isFinite(x)))
    throw unsupported();
  return { matrix, curves };
}
export function toSrgb(data: Uint8ClampedArray, color?: PhotoColor) {
  if (!color) return;
  const { matrix: m, curves: c } = color;
  const encode = Array.from({ length: 4097 }, (_, i) => {
    const x = i / 4096;
    return Math.round(
      255 * (x <= 0.0031308 ? 12.92 * x : 1.055 * x ** (1 / 2.4) - 0.055),
    );
  });
  const byte = (x: number) =>
    encode[Math.max(0, Math.min(4096, Math.round(x * 4096)))]!;
  for (let i = 0; i < data.length; i += 4) {
    const r = c[0]![data[i]!]!,
      g = c[1]![data[i + 1]!]!,
      b = c[2]![data[i + 2]!]!;
    data[i] = byte(m[0]! * r + m[1]! * g + m[2]! * b);
    data[i + 1] = byte(m[3]! * r + m[4]! * g + m[5]! * b);
    data[i + 2] = byte(m[6]! * r + m[7]! * g + m[8]! * b);
  }
}
