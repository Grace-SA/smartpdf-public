import HeicWorker from "./heic.worker?worker&inline";
import { isHeic } from "./heic-header";
import { inspectHeic } from "./heic-inspect";
import { PHOTO_LIMITS } from "./model";
import { readLocalFile } from "../platform/abort";

export async function normalizePhoto(
  file: File,
  signal: AbortSignal,
  notice?: (message: string) => void,
): Promise<File> {
  if (file.size > PHOTO_LIMITS.fileBytes)
    throw new Error("Each image must be at most 15 MiB and 16 megapixels.");
  const bytes = await readLocalFile(file, signal);
  if (!isHeic(bytes)) return file;
  const metadata = inspectHeic(bytes);
  if (metadata.hdrGainMap)
    notice?.(
      "HDR photo: the PDF uses its standard-brightness image. HDR screen highlights are not retained.",
    );
  return new Promise((resolve, reject) => {
    const worker = new HeicWorker();
    let canvas: HTMLCanvasElement | undefined;
    let finished = false;
    const clean = () => {
      finished = true;
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      worker.terminate();
      if (canvas) canvas.width = canvas.height = 0;
    };
    const fail = (message: string) => {
      clean();
      reject(new Error(message));
    };
    const abort = () => fail("Cancelled");
    const timer = setTimeout(
      () => fail("HEIC conversion took too long. Try a smaller photo."),
      60000,
    );
    signal.addEventListener("abort", abort, { once: true });
    worker.onerror = (event) => {
      event.preventDefault();
      fail("HEIC conversion failed. Export a JPEG and try again.");
    };
    worker.onmessage = (event) => {
      if (event.data.error) fail(event.data.error);
      if (event.data.pixels && !finished) {
        worker.terminate();
        try {
          const { width, height, pixels } = event.data;
          if (
            !Number.isInteger(width) ||
            !Number.isInteger(height) ||
            width <= 0 ||
            height <= 0 ||
            width * height > PHOTO_LIMITS.pixels ||
            pixels.length !== width * height * 4
          )
            throw new Error("Invalid HEIC image dimensions.");
          canvas = document.createElement("canvas");
          canvas.width = width;
          canvas.height = height;
          const context = canvas.getContext("2d");
          if (!context)
            throw new Error("HEIC conversion is unavailable in this browser.");
          context.putImageData(
            new ImageData(
              new Uint8ClampedArray(
                pixels.buffer,
                pixels.byteOffset,
                pixels.byteLength,
              ),
              width,
              height,
            ),
            0,
            0,
          );
          context.globalCompositeOperation = "destination-over";
          context.fillStyle = "white";
          context.fillRect(0, 0, width, height);
          canvas.toBlob(
            (blob) => {
              if (finished) return;
              if (!blob || blob.type !== "image/jpeg") {
                fail("HEIC could not be converted to JPEG.");
                return;
              }
              clean();
              resolve(new File([blob], file.name, { type: "image/jpeg" }));
            },
            "image/jpeg",
            0.95,
          );
        } catch {
          fail("HEIC could not be converted to JPEG.");
        }
      }
    };
    if (signal.aborted) abort();
    else {
      try {
        worker.postMessage(bytes, [bytes.buffer]);
      } catch {
        fail("HEIC conversion failed. Export a JPEG and try again.");
      }
    }
  });
}
