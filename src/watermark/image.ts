import { inspectImage } from "../photos/model";
import { inspectImageColor } from "../photos/color-profile";
import { readLocalFile } from "../platform/abort";
import { WATERMARK_LIMITS } from "./model";
import type { WatermarkImage } from "./generate";
export type ImageAsset = WatermarkImage & { url: string; name: string };
export async function watermarkImage(
  file: File,
  signal: AbortSignal,
): Promise<ImageAsset> {
  if (!file.size || file.size > WATERMARK_LIMITS.imageBytes)
    throw Error("Choose a PNG or JPEG up to 5 MiB and 4 MP.");
  const input = await readLocalFile(file, signal),
    info = inspectImage(input);
  if (info.width * info.height > WATERMARK_LIMITS.pixels)
    throw Error("Choose a PNG or JPEG up to 4 megapixels.");
  await inspectImageColor(input, info.format);
  const url = URL.createObjectURL(
    new Blob([input as Uint8Array<ArrayBuffer>], {
      type: info.format === "png" ? "image/png" : "image/jpeg",
    }),
  );
  const image = new Image(),
    canvas = document.createElement("canvas");
  let rejectDecode: (error: Error) => void = () => {};
  const cancelled = new Promise<never>((_, reject) => {
    rejectDecode = reject;
  });
  const timer = setTimeout(
    () =>
      rejectDecode(
        Error(
          "This watermark image took too long to decode. Choose another PNG or JPEG.",
        ),
      ),
    15000,
  );
  const abort = () => {
    image.src = "";
    rejectDecode(Error("Cancelled"));
  };
  signal.addEventListener("abort", abort, { once: true });
  try {
    if (signal.aborted) throw Error("Cancelled");
    image.src = url;
    await Promise.race([image.decode(), cancelled]);
    if (signal.aborted) throw Error("Cancelled");
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    if (
      !canvas.width ||
      !canvas.height ||
      canvas.width * canvas.height > WATERMARK_LIMITS.pixels
    )
      throw Error("The watermark image exceeds its pixel budget.");
    const context = canvas.getContext("2d")!;
    context.drawImage(image, 0, 0);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let visible = false;
    for (let i = 3; i < pixels.length; i += 4)
      if (pixels[i]! > 8) {
        visible = true;
        break;
      }
    if (!visible)
      throw Error(
        "This image is fully transparent. Choose a visible watermark image.",
      );
    const encoded = canvas.toDataURL("image/png").split(",")[1];
    if (!encoded || encoded.length > (WATERMARK_LIMITS.imageBytes * 4) / 3 + 4)
      throw Error(
        "The normalized watermark image is too large. Choose a smaller PNG or JPEG.",
      );
    const bytes = Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0));
    if (signal.aborted) throw Error("Cancelled");
    return {
      bytes,
      width: canvas.width,
      height: canvas.height,
      url: URL.createObjectURL(new Blob([bytes], { type: "image/png" })),
      name: file.name,
    };
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", abort);
    URL.revokeObjectURL(url);
    image.src = "";
    canvas.width = canvas.height = 0;
  }
}
