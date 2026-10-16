import { inspectPdf } from "../combine/generate";
import { rotatePdf, rotateErrors } from "./generate";
console.log = () => undefined;
console.warn = () => undefined;
self.onmessage = async (
  event: MessageEvent<{
    bytes: Uint8Array;
    turns: number[];
    inspect?: boolean;
  }>,
) => {
  try {
    if (event.data.inspect) {
      self.postMessage({ result: await inspectPdf(event.data.bytes) });
      return;
    }
    const bytes = await rotatePdf(event.data.bytes, event.data.turns);
    self.postMessage({ bytes }, { transfer: [bytes.buffer as ArrayBuffer] });
  } catch (error) {
    const code =
      Object.entries(rotateErrors).find(
        ([, message]) => error instanceof Error && message === error.message,
      )?.[0] ?? "output";
    self.postMessage({ failed: true, code });
  }
};
