import { beforeEach, afterEach, test, expect, vi } from "vitest";
type MockWorker = {
  onmessage: ((e: MessageEvent) => void) | null;
  onerror: ((e: ErrorEvent) => void) | null;
  terminated: boolean;
  postMessage: (m: unknown) => void;
  terminate: () => void;
};
const mocks = vi.hoisted(() => ({
  instances: [] as MockWorker[],
  received: [] as unknown[],
}));
vi.mock("../src/unlock/unlock.worker?worker&inline", () => ({
  default: class {
    onmessage: MockWorker["onmessage"] = null;
    onerror: MockWorker["onerror"] = null;
    terminated = false;
    constructor() {
      mocks.instances.push(this);
    }
    postMessage(m: unknown) {
      mocks.received.push(structuredClone(m));
    }
    terminate() {
      this.terminated = true;
    }
  },
}));
let unlockOperation: typeof import("../src/unlock/service").unlockOperation;
const file = () => new File(["%PDF-1.7\n%%EOF"], "synthetic.pdf");
const wasm = new Uint8Array([0, 97, 115, 109, 1, 0, 0, 0]);
beforeEach(async () => {
  vi.resetModules();
  ({ unlockOperation } = await import("../src/unlock/service"));
  mocks.instances.length = 0;
  mocks.received.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(wasm, { status: 200 })),
  );
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
test("successful inspection destroys worker and listeners, and sends no input names", async () => {
  const promise = unlockOperation(
    file(),
    { kind: "inspect" },
    new AbortController().signal,
  );
  await vi.waitFor(() => expect(mocks.instances).toHaveLength(1));
  const worker = mocks.instances[0]!;
  expect(JSON.stringify(mocks.received)).not.toContain("synthetic.pdf");
  worker.onmessage?.(
    new MessageEvent("message", {
      data: {
        kind: "result",
        ok: true,
        result: { status: "password-required" },
      },
    }),
  );
  await expect(promise).resolves.toEqual({ status: "password-required" });
  expect(worker.terminated).toBe(true);
  expect(worker.onmessage).toBeNull();
  expect(worker.onerror).toBeNull();
});
test("abort terminates an active operation and late replies cannot succeed", async () => {
  const controller = new AbortController();
  const promise = unlockOperation(
    file(),
    { kind: "unlock", password: "synthetic-password", ordinary: false },
    controller.signal,
  );
  const rejected = expect(promise).rejects.toThrow("cancelled");
  await vi.waitFor(() => expect(mocks.instances).toHaveLength(1));
  const worker = mocks.instances[0]!;
  controller.abort();
  await rejected;
  expect(worker.terminated).toBe(true);
  expect(worker.onmessage).toBeNull();
});
test("raw worker messages never become public errors and a retry uses a fresh worker", async () => {
  const first = unlockOperation(
    file(),
    { kind: "inspect" },
    new AbortController().signal,
  );
  const rejected = expect(first).rejects.toThrow("engine");
  await vi.waitFor(() => expect(mocks.instances).toHaveLength(1));
  mocks.instances[0]!.onmessage?.(
    new MessageEvent("message", {
      data: { kind: "result", ok: false, reason: "raw-sensitive-diagnostic" },
    }),
  );
  await rejected;
  const second = unlockOperation(
    file(),
    { kind: "inspect" },
    new AbortController().signal,
  );
  await vi.waitFor(() => expect(mocks.instances).toHaveLength(2));
  mocks.instances[1]!.onmessage?.(
    new MessageEvent("message", {
      data: { kind: "result", ok: true, result: { status: "accessible" } },
    }),
  );
  await expect(second).resolves.toEqual({ status: "accessible" });
  expect(mocks.instances.every((w) => w.terminated)).toBe(true);
});
test("deadline terminates worker rather than leaving decrypting data alive", async () => {
  vi.useFakeTimers();
  const promise = unlockOperation(
    file(),
    { kind: "inspect" },
    new AbortController().signal,
  );
  const rejected = expect(promise).rejects.toThrow("timeout");
  await vi.advanceTimersByTimeAsync(1);
  expect(mocks.instances).toHaveLength(1);
  await vi.advanceTimersByTimeAsync(120000);
  await rejected;
  expect(mocks.instances[0]!.terminated).toBe(true);
});
test("already aborted and oversized requests never start a worker", async () => {
  const controller = new AbortController();
  controller.abort();
  await expect(
    unlockOperation(file(), { kind: "inspect" }, controller.signal),
  ).rejects.toThrow("cancelled");
  const big = { size: 100 * 1024 * 1024 } as File;
  await expect(
    unlockOperation(big, { kind: "inspect" }, new AbortController().signal),
  ).rejects.toThrow("resource");
  expect(mocks.instances).toHaveLength(0);
});
test("cancel is immediate while the engine resource is still loading", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise(() => {})),
  );
  const controller = new AbortController();
  const operation = unlockOperation(
    file(),
    { kind: "inspect" },
    controller.signal,
  );
  const rejected = expect(operation).rejects.toThrow("cancelled");
  await Promise.resolve();
  controller.abort();
  await rejected;
  expect(mocks.instances).toHaveLength(0);
});
test("a bad successful WASM response is not cached and can recover", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(new Response("not wasm", { status: 200 }))
    .mockResolvedValueOnce(new Response(wasm, { status: 200 }));
  vi.stubGlobal("fetch", fetcher);
  await expect(
    unlockOperation(file(), { kind: "inspect" }, new AbortController().signal),
  ).rejects.toThrow("engine");
  const operation = unlockOperation(
    file(),
    { kind: "inspect" },
    new AbortController().signal,
  );
  await vi.waitFor(() => expect(mocks.instances).toHaveLength(1));
  mocks.instances[0]!.onmessage?.(
    new MessageEvent("message", {
      data: { kind: "result", ok: true, result: { status: "accessible" } },
    }),
  );
  await expect(operation).resolves.toEqual({ status: "accessible" });
  expect(fetcher).toHaveBeenCalledTimes(2);
});
