/** Installed inside the dedicated PDF.js worker, never on the page. */
export function installMemoryResources() {
  const prefix = "https://smartpdf-resources.invalid/";
  let resources: Record<string, Uint8Array> = {};
  const read = (url: string) => {
    if (!url.startsWith(prefix)) throw Error("RESOURCE_NOT_PRELOADED");
    const data = resources[url.slice(prefix.length)];
    if (!(data instanceof Uint8Array)) throw Error("RESOURCE_NOT_PRELOADED");
    return data.slice().buffer as ArrayBuffer;
  };
  globalThis.addEventListener("message", (event: MessageEvent) => {
    if (!event.data?.smartPdfResources) return;
    resources = event.data.smartPdfResources;
    globalThis.postMessage({ smartPdfResourcesReady: true });
  });
  // Both asynchronous PDF.js resources and synchronous qcms/ICC reads use
  // already-loaded static bytes. Unknown URLs never fall through to a network.
  globalThis.fetch = async (input: RequestInfo | URL) => {
    const url = input instanceof Request ? input.url : String(input);
    const body = read(url);
    return new Response(body, {
      headers: {
        "Content-Type": url.endsWith(".wasm")
          ? "application/wasm"
          : "application/octet-stream",
      },
    });
  };
  class MemoryRequest {
    response: ArrayBuffer | null = null;
    responseType = "";
    private url = "";
    open(method: string, url: string, asynchronous = true) {
      if (method !== "GET" || asynchronous)
        throw Error("RESOURCE_NOT_PRELOADED");
      this.url = url;
    }
    send() {
      this.response = read(this.url);
    }
  }
  globalThis.XMLHttpRequest = MemoryRequest as unknown as typeof XMLHttpRequest;
}

export const resourceOrigin = "https://smartpdf-resources.invalid/";
