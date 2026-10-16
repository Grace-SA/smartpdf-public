import { generatePhotos, type PhotoInput } from "./generate";
import type { PhotoSettings } from "./model";
console.log = () => undefined;
console.warn = () => undefined;
self.onmessage = async (
  event: MessageEvent<{ inputs: PhotoInput[]; settings: PhotoSettings }>,
) => {
  try {
    const bytes = await generatePhotos(
      event.data.inputs,
      event.data.settings,
      (done) => self.postMessage({ done }),
    );
    self.postMessage({ bytes }, { transfer: [bytes.buffer as ArrayBuffer] });
  } catch {
    self.postMessage({ failed: true });
  }
};
self.postMessage({ ready: true });
