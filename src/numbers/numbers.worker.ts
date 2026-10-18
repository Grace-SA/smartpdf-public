import { inspectNumbers, numberPdf } from "./generate";
import type { NumberSettings } from "./model";
console.log = () => undefined;
console.warn = () => undefined;
self.onmessage = async (
  event: MessageEvent<{
    input: Uint8Array;
    settings?: NumberSettings;
    font?: Uint8Array;
  }>,
) => {
  try {
    if (!event.data.settings) {
      const { geometry, annotations } = await inspectNumbers(event.data.input);
      self.postMessage({ inspection: { geometry, annotations } });
    } else {
      const output = await numberPdf(
        event.data.input,
        event.data.settings,
        event.data.font!,
        (stage) => self.postMessage({ stage }),
      );
      self.postMessage(
        { output },
        { transfer: [output.buffer as ArrayBuffer] },
      );
    }
  } catch (error) {
    self.postMessage({
      error:
        error instanceof Error
          ? error.message
          : "Page numbering could not finish. Your original is unchanged.",
    });
  }
};
self.postMessage({ ready: true });
