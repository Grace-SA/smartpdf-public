import { prepareCredentialCopy } from "../core/credential-copy";
import { prepareOrdinaryCopy } from "../core/ordinary-copy";
console.warn = () => undefined;
console.log = () => undefined;
self.onmessage = async (
  event: MessageEvent<{
    bytes: Uint8Array;
    confirmed: boolean;
    ordinary?: boolean;
  }>,
) => {
  try {
    const bytes = await (
      event.data.ordinary ? prepareOrdinaryCopy : prepareCredentialCopy
    )(event.data.bytes, event.data.confirmed);
    self.postMessage({ ok: true, bytes });
  } catch {
    self.postMessage({ ok: false });
  }
};
