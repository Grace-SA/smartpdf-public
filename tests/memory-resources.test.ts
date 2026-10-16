import { test, expect, vi } from "vitest";
import {
  installMemoryResources,
  resourceOrigin,
} from "../src/platform/memory-resources";

test("worker resources serve isolated static bytes and never fall through to network", async () => {
  let receive: (event: MessageEvent) => void = () => {};
  const post = vi.fn();
  vi.stubGlobal("addEventListener", (_: string, callback: typeof receive) => {
    receive = callback;
  });
  vi.stubGlobal("postMessage", post);
  const oldFetch = globalThis.fetch;
  const oldXhr = globalThis.XMLHttpRequest;
  try {
    installMemoryResources();
    receive({
      data: {
        smartPdfResources: { "wasmUrl/test.wasm": new Uint8Array([1, 2, 3]) },
      },
    } as MessageEvent);
    expect(post).toHaveBeenCalledWith({ smartPdfResourcesReady: true });
    const response = await fetch(resourceOrigin + "wasmUrl/test.wasm");
    expect(response.headers.get("content-type")).toBe("application/wasm");
    expect(new Uint8Array(await response.arrayBuffer())).toEqual(
      new Uint8Array([1, 2, 3]),
    );
    const xhr = new XMLHttpRequest();
    xhr.open("GET", resourceOrigin + "wasmUrl/test.wasm", false);
    xhr.send();
    const bytes = new Uint8Array(xhr.response);
    bytes[0] = 9;
    expect(
      new Uint8Array(
        await (await fetch(resourceOrigin + "wasmUrl/test.wasm")).arrayBuffer(),
      )[0],
    ).toBe(1);
    await expect(fetch("https://example.com/document.pdf")).rejects.toThrow(
      "RESOURCE_NOT_PRELOADED",
    );
    await expect(fetch(resourceOrigin + "unknown")).rejects.toThrow(
      "RESOURCE_NOT_PRELOADED",
    );
    expect(() =>
      xhr.open("POST", resourceOrigin + "wasmUrl/test.wasm", false),
    ).toThrow();
  } finally {
    globalThis.fetch = oldFetch;
    globalThis.XMLHttpRequest = oldXhr;
    vi.unstubAllGlobals();
  }
});
