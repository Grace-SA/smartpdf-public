import { probePdf } from "../core/probe";
// Library diagnostics can contain input text. Only stable results cross this boundary.
console.warn = () => undefined;
console.log = () => undefined;
self.onmessage = async (
  event: MessageEvent<{ id: number; bytes: Uint8Array }>,
) => {
  const { id, bytes } = event.data;
  self.postMessage({ id, result: await probePdf(bytes, "preview") });
};
self.postMessage({ ready: true });
