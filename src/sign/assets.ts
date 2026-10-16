import { readLocalFile } from "../platform/abort";
import coverage from "./font-coverage.json";
import { inspectImage } from "../photos/model";
import { SIGN_LIMITS, newSignatureId, type SignatureAsset } from "./model";
export const styles = [
  { id: "MaShanZheng", label: "Brush", file: "MaShanZheng-Regular.ttf" },
  { id: "Kalam", label: "Handwritten", file: "Kalam-Regular.ttf" },
  { id: "Caveat", label: "Flowing", file: "Caveat.ttf" },
] as const;
export function supportsName(id: string, name: string) {
  if (name.length > SIGN_LIMITS.nameLength) return false;
  const ranges = (coverage as Record<string, number[][]>)[id] ?? [];
  return (
    !!name.trim() &&
    [...name].every((c) =>
      ranges.some(
        ([a, b]) => c.codePointAt(0)! >= a! && c.codePointAt(0)! <= b!,
      ),
    )
  );
}
const fontLoads = new Map<string, Promise<void>>();
export function prepareSignFont(id: string): Promise<void> {
  const existing = fontLoads.get(id);
  if (existing) return existing;
  const style = styles.find((item) => item.id === id);
  if (!style) return Promise.reject(new Error("Unknown signature font."));
  const loading = (async () => {
    const res = await fetch("/sign-fonts/" + style.file, {
      signal: AbortSignal.timeout(30_000),
    });
    if (!res.ok) throw Error("Signature font could not load. Please retry.");
    const face = new FontFace(style.id, await res.arrayBuffer());
    await face.load();
    document.fonts.add(face);
  })().catch((error: unknown) => {
    fontLoads.delete(id);
    throw error;
  });
  fontLoads.set(id, loading);
  return loading;
}
export async function prepareSignFonts(signal: AbortSignal) {
  if (signal.aborted) throw Error("Cancelled");
  await Promise.all(styles.map((style) => prepareSignFont(style.id)));
  if (signal.aborted) throw Error("Cancelled");
}
export async function canvasAsset(
  canvas: HTMLCanvasElement,
): Promise<SignatureAsset> {
  if (
    !canvas.width ||
    !canvas.height ||
    canvas.width * canvas.height > SIGN_LIMITS.pixels
  )
    throw Error("Signature image exceeds the pixel budget.");
  const pixels = canvas
    .getContext("2d")!
    .getImageData(0, 0, canvas.width, canvas.height).data;
  let visible = false;
  for (let i = 0; i < pixels.length; i += 4) {
    if (
      pixels[i + 3]! > 8 &&
      (pixels[i]! < 245 || pixels[i + 1]! < 245 || pixels[i + 2]! < 245)
    ) {
      visible = true;
      break;
    }
  }
  if (!visible)
    throw Error(
      "This image is blank or transparent. Choose an image with a visible signature.",
    );
  // WebKit can fail Blob reads while its network context is offline, even
  // for a locally generated canvas. Decode the bounded canvas PNG directly.
  const encoded = canvas.toDataURL("image/png").split(",")[1];
  if (!encoded || encoded.length > (SIGN_LIMITS.imageBytes * 4) / 3 + 4)
    throw Error("Signature is too large. Use a smaller image.");
  const bytes = Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0));
  const blob = new Blob([bytes], { type: "image/png" });
  return {
    id: newSignatureId(),
    bytes,
    width: canvas.width,
    height: canvas.height,
    url: URL.createObjectURL(blob),
  };
}
export async function typedAsset(name: string, font: string, color: string) {
  if (name.length > SIGN_LIMITS.nameLength || !supportsName(font, name))
    throw Error("Choose a font that supports every character in your name.");
  await prepareSignFont(font);
  await document.fonts.ready;
  const c = document.createElement("canvas"),
    ctx = c.getContext("2d")!;
  ctx.font = `128px "${font}"`;
  const m = ctx.measureText(name.trim());
  const left = Math.max(0, m.actualBoundingBoxLeft),
    right = Math.max(m.width, m.actualBoundingBoxRight),
    top = Math.max(1, m.actualBoundingBoxAscent),
    bottom = Math.max(1, m.actualBoundingBoxDescent);
  const scale = Math.min(1, 2000 / (left + right + 24));
  c.width = Math.ceil((left + right + 24) * scale);
  c.height = Math.ceil((top + bottom + 24) * scale);
  ctx.scale(scale, scale);
  ctx.font = `128px "${font}"`;
  ctx.fillStyle = color;
  ctx.fillText(name.trim(), left + 12, top + 12);
  try {
    return await canvasAsset(c);
  } finally {
    c.width = c.height = 0;
  }
}
export async function importedAsset(file: File) {
  if (file.size > SIGN_LIMITS.imageBytes)
    throw Error("Use a PNG or JPEG up to 5 MiB and 4 megapixels.");
  const bytes = await readLocalFile(file, new AbortController().signal),
    info = inspectImage(bytes);
  if (info.width * info.height > SIGN_LIMITS.pixels)
    throw Error("Use a signature image up to 4 megapixels.");
  const url = URL.createObjectURL(
    new Blob([new Uint8Array(bytes)], {
      type: info.format === "png" ? "image/png" : "image/jpeg",
    }),
  );
  const img = new Image();
  try {
    img.src = url;
    await img.decode();
    const c = document.createElement("canvas");
    c.width = img.naturalWidth;
    c.height = img.naturalHeight;
    c.getContext("2d")!.drawImage(img, 0, 0);
    try {
      return await canvasAsset(c);
    } finally {
      c.width = c.height = 0;
    }
  } finally {
    URL.revokeObjectURL(url);
    img.src = "";
  }
}
