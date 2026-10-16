import { probePdf } from "../core/probe";
// Library diagnostics can contain input text. Only stable results cross this boundary.
console.warn = () => undefined;
console.log = () => undefined;
self.onmessage = async (
  event: MessageEvent<{
    id: number;
    bytes: Uint8Array;
    syntheticDiagnostics?: boolean;
  }>,
) => {
  const { id, bytes } = event.data;
  if (event.data.syntheticDiagnostics) {
    Reflect.set(globalThis, "syntheticProbeStage", (stage: string) =>
      self.postMessage({ syntheticStage: stage }),
    );
    self.postMessage({ syntheticStage: "received" });
  }
  self.postMessage({ id, result: await probePdf(bytes, "preview") });
};
self.postMessage({ ready: true });
