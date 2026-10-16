import { combinePdfs, inspectPdf } from "./generate";
import { failureMessageCode } from "./failure-messages";
console.log = () => undefined;
console.warn = () => undefined;
self.onmessage = async (
  event: MessageEvent<{
    operation: "inspect" | "combine";
    inputs: Uint8Array[];
  }>,
) => {
  try {
    if (event.data.operation === "inspect") {
      self.postMessage({ result: await inspectPdf(event.data.inputs[0]!) });
    } else {
      const bytes = await combinePdfs(
        event.data.inputs,
        (done) => self.postMessage({ done }),
        (stage) => self.postMessage({ stage }),
      );
      self.postMessage({ bytes }, { transfer: [bytes.buffer as ArrayBuffer] });
    }
  } catch (error) {
    self.postMessage({ failed: true, failureCode: failureMessageCode(error) });
  }
};
self.postMessage({ ready: true });
