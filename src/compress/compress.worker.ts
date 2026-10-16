/// <reference lib="webworker" />
import createQpdf from "@neslinesli93/qpdf-wasm";
import { compressionArgs, type CompressionLevel } from "./model";
import { recompressCommonImages } from "./images";

type PrepareRequest = { kind: "prepare"; wasmUrl: string };
type CompressRequest = {
  kind: "compress";
  id: number;
  bytes: ArrayBuffer;
  level: CompressionLevel;
};
type Request = PrepareRequest | CompressRequest;

let engine: Awaited<ReturnType<typeof createQpdf>> | null = null;
let preparation: Promise<Awaited<ReturnType<typeof createQpdf>>> | null = null;

async function encodeJpeg(
  rgb: Uint8Array,
  width: number,
  height: number,
  quality: number,
) {
  if (typeof OffscreenCanvas === "undefined")
    throw new Error("Canvas image compression is unavailable.");
  const canvas = new OffscreenCanvas(width, height);
  const context = canvas.getContext("2d", { alpha: false });
  if (!context || typeof canvas.convertToBlob !== "function")
    throw new Error("Canvas image compression is unavailable.");
  const rgba = new Uint8ClampedArray(width * height * 4);
  for (let source = 0, target = 0; source < rgb.length; source += 3) {
    rgba[target] = rgb[source]!;
    rgba[target + 1] = rgb[source + 1]!;
    rgba[target + 2] = rgb[source + 2]!;
    rgba[target + 3] = 255;
    target += 4;
  }
  context.putImageData(new ImageData(rgba, width, height), 0, 0);
  const blob = await canvas.convertToBlob({ type: "image/jpeg", quality });
  return new Uint8Array(await blob.arrayBuffer());
}

async function prepare(wasmUrl: string) {
  if (!preparation) {
    preparation = createQpdf({
      locateFile: () => wasmUrl,
      noInitialRun: true,
    } as Parameters<typeof createQpdf>[0]);
  }
  engine = await preparation;
  return engine;
}

self.onmessage = async (event: MessageEvent<Request>) => {
  if (event.data.kind === "prepare") {
    try {
      await prepare(event.data.wasmUrl);
      self.postMessage({ kind: "prepared", ok: true });
    } catch (error) {
      self.postMessage({
        kind: "prepared",
        ok: false,
        message:
          error instanceof Error && error.message
            ? error.message
            : "The local compression engine could not load.",
      });
    }
    return;
  }

  const { id, bytes: source, level } = event.data;
  try {
    if (!engine) throw new Error("The local compression engine is not ready.");
    const input = `/input-${id}.pdf`;
    const output = `/output-${id}.pdf`;
    const structureOutput = `/structure-output-${id}.pdf`;
    const imageInput = `/image-input-${id}.pdf`;
    const imageOutput = `/image-output-${id}.pdf`;
    const fs = engine.FS as typeof engine.FS & {
      writeFile: (path: string, bytes: Uint8Array) => void;
      unlink: (path: string) => void;
    };
    const original = new Uint8Array(source);
    let prepared: Awaited<ReturnType<typeof recompressCommonImages>> | null =
      null;
    if (level !== "quality") {
      try {
        prepared = await recompressCommonImages(original, level, encodeJpeg);
      } catch {
        // Optional image work must never block ordinary qpdf compression.
      }
    }
    fs.writeFile(input, original);
    try {
      engine.callMain([...compressionArgs(level), input, output]);
      let best = fs.readFile(output).slice();
      if (level !== "quality" && best.byteLength >= original.byteLength) {
        engine.callMain([
          ...compressionArgs("quality"),
          input,
          structureOutput,
        ]);
        const structureOnly = fs.readFile(structureOutput).slice();
        if (structureOnly.byteLength < best.byteLength) best = structureOnly;
      }
      if (
        prepared &&
        prepared.replacedImages > 0 &&
        prepared.bytes.byteLength < best.byteLength
      ) {
        try {
          best = prepared.bytes.slice();
          fs.writeFile(imageInput, prepared.bytes);
          engine.callMain([...compressionArgs(level), imageInput, imageOutput]);
          const optimizedImages = fs.readFile(imageOutput).slice();
          if (optimizedImages.byteLength < best.byteLength)
            best = optimizedImages;
        } catch {
          // Optional image work must never displace the ordinary qpdf result.
        }
      }
      const bytes = new Uint8Array(best).slice().buffer;
      self.postMessage(
        { kind: "compressed", id, ok: true, bytes },
        { transfer: [bytes] },
      );
    } finally {
      try {
        fs.unlink(input);
      } catch {
        // A failed qpdf call may already have removed the input.
      }
      try {
        fs.unlink(output);
      } catch {
        // Failed qpdf calls do not create an output.
      }
      try {
        fs.unlink(structureOutput);
      } catch {
        // A smaller first candidate does not need the structural fallback.
      }
      try {
        fs.unlink(imageInput);
      } catch {
        // No eligible common images means there is no second input.
      }
      try {
        fs.unlink(imageOutput);
      } catch {
        // A larger image-only candidate does not run the second qpdf pass.
      }
    }
  } catch (error) {
    self.postMessage({
      kind: "compressed",
      id,
      ok: false,
      message:
        error instanceof Error && error.message
          ? error.message
          : "Compression could not finish.",
    });
  }
};
