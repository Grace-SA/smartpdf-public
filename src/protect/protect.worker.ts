/// <reference lib="webworker" />
import { inspectProtect } from "./structure";
import { generateProtected } from "./generate";
import { ProtectFailure } from "./model";
import { limitWasmHeap } from "../unlock/memory";
import createQpdf from "@neslinesli93/qpdf-wasm";

console.log = console.warn = console.error = () => {};
let started = false;
self.onmessage = async (
  event: MessageEvent<{
    kind: "inspect" | "protect";
    bytes: ArrayBuffer;
    password?: string;
    wasm?: ArrayBuffer;
  }>,
) => {
  if (started) return;
  started = true;
  const secret = { value: event.data.password ?? "" };
  event.data.password = "";
  const heap = limitWasmHeap();
  const nativeFetch = self.fetch;
  try {
    if (event.data.kind === "inspect") {
      const result = await inspectProtect(new Uint8Array(event.data.bytes));
      self.postMessage({ ok: true, pages: result.pages });
      return;
    }
    if (
      !crypto?.getRandomValues ||
      !crypto.subtle ||
      !(event.data.wasm instanceof ArrayBuffer)
    )
      throw new ProtectFailure("ENGINE");
    const wasm = new Uint8Array(event.data.wasm);
    // The inline worker consumes transferred public bytes in its own realm.
    // It never fetches documents, passwords or a blob URL across CSP realms.
    self.fetch = async (input) => {
      if (typeof input !== "string" || input !== "/qpdf.wasm")
        throw new ProtectFailure("ENGINE");
      return new Response(wasm.slice(), {
        headers: { "content-type": "application/wasm" },
      });
    };
    const engine = await createQpdf({
      locateFile: () => "/qpdf.wasm",
      noFSInit: true,
      preRun: [
        (m: {
          FS: {
            init: (
              a: () => null,
              b: (n: number) => void,
              c: (n: number) => void,
            ) => void;
          };
        }) =>
          m.FS.init(
            () => null,
            () => {},
            () => {},
          ),
      ],
    } as Parameters<typeof createQpdf>[0]);
    const result = await generateProtected(
      new Uint8Array(event.data.bytes),
      secret.value,
      engine,
    );
    const bytes = result.bytes.slice().buffer;
    self.postMessage(
      { ok: true, pages: result.pages, bytes },
      { transfer: [bytes] },
    );
  } catch (error) {
    self.postMessage({
      ok: false,
      code: heap.exhausted()
        ? "RESOURCE"
        : error instanceof ProtectFailure
          ? error.code
          : "ENGINE",
    });
  } finally {
    secret.value = "";
    self.fetch = nativeFetch;
    heap.restore();
    self.close();
  }
};
