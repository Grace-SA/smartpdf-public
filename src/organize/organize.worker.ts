import { organizePdf, organizeErrors, inspectOrganize } from "./generate";
import type { PageEntry } from "./model";
console.log = () => undefined;
console.warn = () => undefined;
self.onmessage = async (
  event: MessageEvent<{
    bytes: Uint8Array;
    operation?: "inspect";
    plan: PageEntry[];
    adjustDeletedAssociations?: boolean;
  }>,
) => {
  try {
    if (event.data.operation === "inspect") {
      self.postMessage({ result: await inspectOrganize(event.data.bytes) });
      return;
    }
    const bytes = await organizePdf(
      event.data.bytes,
      event.data.plan,
      event.data.adjustDeletedAssociations,
    );
    self.postMessage({ bytes }, { transfer: [bytes.buffer as ArrayBuffer] });
  } catch (error) {
    const messages = Object.values(organizeErrors);
    self.postMessage({
      failed: true,
      code:
        error instanceof Error
          ? messages.findIndex((m) => m === error.message)
          : -1,
    });
  }
};
self.postMessage({ ready: true });
