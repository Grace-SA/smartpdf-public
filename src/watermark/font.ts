import { glyphShape, type TextShape } from "../overlay/text";
import { normalizedText, WATERMARK_LIMITS } from "./model";
let resource: Promise<Uint8Array> | null = null;
export function prepareWatermark(signal: AbortSignal) {
  if (!resource)
    resource = fetch("/watermark-fonts/SmartPDFSans-Regular.ttf", { signal })
      .then(async (response) => {
        if (!response.ok)
          throw Error("The watermark font could not load. Retry this tool.");
        const bytes = new Uint8Array(await response.arrayBuffer());
        if (bytes.length > WATERMARK_LIMITS.fontBytes)
          throw Error("The watermark font exceeds its budget.");
        return bytes;
      })
      .catch((error) => {
        resource = null;
        throw error;
      });
  return resource;
}
export type { TextShape };
export function textShape(bytes: Uint8Array, value: string): TextShape {
  const text = normalizedText(value);
  try {
    return glyphShape(bytes, text);
  } catch (error) {
    if (
      error instanceof Error &&
      error.message.startsWith("The font does not support")
    )
      throw Error(
        error.message.replace("The font", "The watermark font") +
          " Use supported text or an image watermark.",
        { cause: error },
      );
    throw error;
  }
}
