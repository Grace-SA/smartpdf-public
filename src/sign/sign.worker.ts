import { inspectSign, signPdf } from "./generate";
import type { Placement } from "./model";
console.warn = () => undefined;
console.log = () => undefined;
self.onmessage = async (
  e: MessageEvent<{
    bytes: Uint8Array;
    inspect?: boolean;
    assets: { id: string; bytes: Uint8Array }[];
    placements: Placement[];
  }>,
) => {
  try {
    if (e.data.inspect) {
      const { geometry } = await inspectSign(e.data.bytes);
      self.postMessage({ geometry });
    } else {
      const bytes = await signPdf(
        e.data.bytes,
        e.data.assets,
        e.data.placements,
        (stage) => self.postMessage({ stage }),
      );
      self.postMessage({ bytes }, { transfer: [bytes.buffer as ArrayBuffer] });
    }
  } catch (e) {
    self.postMessage({
      error:
        e instanceof Error
          ? e.message
          : "Signing failed. Your draft is unchanged.",
    });
  }
};
