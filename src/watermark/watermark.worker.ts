import {
  inspectWatermark,
  watermarkPdf,
  type WatermarkImage,
} from "./generate";
import type { WatermarkSettings } from "./model";
console.log = () => undefined;
console.warn = () => undefined;
self.onmessage = async (
  event: MessageEvent<{
    input: Uint8Array;
    inspect?: boolean;
    settings: WatermarkSettings;
    font: Uint8Array;
    image?: WatermarkImage;
  }>,
) => {
  try {
    if (event.data.inspect) {
      const { geometry, annotations } = await inspectWatermark(
        event.data.input,
      );
      self.postMessage({ inspection: { geometry, annotations } });
    } else {
      const output = await watermarkPdf(
        event.data.input,
        event.data.settings,
        event.data.font,
        event.data.image,
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
          : "Watermarking failed. Your original is unchanged.",
    });
  }
};
