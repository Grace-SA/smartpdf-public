import libheif from "libheif-js/libheif-wasm/libheif-bundle.mjs";
import { inspectHeic } from "./heic-inspect";
import { PHOTO_LIMITS, photoCopy } from "./model";
import { toSrgb } from "./heic-color";

console.log = console.warn = () => undefined;
self.onmessage = async (event: MessageEvent<Uint8Array>) => {
  try {
    const { color } = inspectHeic(event.data);
    const engine = await libheif();
    const images = new engine.HeifDecoder().decode(event.data);
    if (!images.length)
      throw new Error(
        "HEIC could not be decoded. Export a JPEG and try again.",
      );
    if (images.length !== 1)
      throw new Error(
        "Choose a HEIC with one still photo. Multi-photo HEIC files are not supported.",
      );
    const image = images[0]!;
    const width = image.get_width(),
      height = image.get_height();
    if (!width || !height || width * height > PHOTO_LIMITS.pixels)
      throw new Error(photoCopy.large);
    const pixels = new ImageData(width, height);
    await new Promise<void>((resolve, reject) =>
      image.display(pixels, (result) =>
        result
          ? resolve()
          : reject(
              new Error(
                "HEIC could not be decoded. Export a JPEG and try again.",
              ),
            ),
      ),
    );
    toSrgb(pixels.data, color);
    image.free();
    self.postMessage(
      { pixels: pixels.data, width, height },
      { transfer: [pixels.data.buffer] },
    );
  } catch (error) {
    self.postMessage({
      error: error instanceof Error ? error.message : "HEIC conversion failed.",
    });
  }
};
self.postMessage({ ready: true });
