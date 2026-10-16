import { splitPdf } from "./generate";
console.log = () => undefined;
console.warn = () => undefined;
self.onmessage = async (
  e: MessageEvent<{
    bytes: Uint8Array;
    groups: number[][];
    adjust: boolean;
    budget: number;
  }>,
) => {
  try {
    const { bytes, groups, adjust, budget } = e.data;
    const outputs = await splitPdf(bytes, groups, adjust, budget, (done) =>
      self.postMessage({ done }),
    );
    self.postMessage(
      { outputs },
      { transfer: outputs.map((b) => b.buffer as ArrayBuffer) },
    );
  } catch (error) {
    self.postMessage({
      error:
        error instanceof Error
          ? error.message
          : "Splitting failed. No results were published.",
    });
  }
};
