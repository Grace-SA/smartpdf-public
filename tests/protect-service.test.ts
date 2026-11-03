import { afterEach, beforeEach, expect, test, vi } from "vitest";
type Port = {
  onmessage: ((e: MessageEvent) => void) | null;
  onerror: ((e: ErrorEvent) => void) | null;
  onmessageerror: ((e: MessageEvent) => void) | null;
  terminated: boolean;
  terminate: () => void;
};
const mock = vi.hoisted(() => ({
  ports: [] as Port[],
  sent: [] as Record<string, unknown>[],
  payloads: [] as Record<string, unknown>[],
  constructorFails: false,
  sendFails: false,
}));
vi.mock("../src/protect/protect.worker?worker&inline", () => ({
  default: class {
    onmessage: Port["onmessage"] = null;
    onerror: Port["onerror"] = null;
    onmessageerror: Port["onmessageerror"] = null;
    terminated = false;
    constructor() {
      if (mock.constructorFails) throw Error("sensitive-constructor");
      mock.ports.push(this);
    }
    postMessage(message: Record<string, unknown>) {
      mock.sent.push(structuredClone(message));
      mock.payloads.push(message);
      if (mock.sendFails) throw Error("sensitive-send");
    }
    terminate() {
      this.terminated = true;
    }
  },
}));
vi.mock("../src/protect/verify", () => ({
  prepareVerifier: vi.fn(async () => "blob:public-reader"),
}));
let protectJob: typeof import("../src/protect/service").protectJob;
const file = () => new File(["%PDF-1.7\n%%EOF"], "synthetic-private-name.pdf");
const wasm = new Uint8Array([0, 97, 115, 109, 1, 0, 0, 0]);
const signal = () => new AbortController().signal;
const reply = (data: unknown) =>
  mock.ports.at(-1)!.onmessage?.(new MessageEvent("message", { data }));
beforeEach(async () => {
  vi.resetModules();
  mock.ports.length = mock.sent.length = mock.payloads.length = 0;
  mock.constructorFails = mock.sendFails = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(wasm)),
  );
  ({ protectJob } = await import("../src/protect/service"));
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
test("inspection has no password or filename and destroys its one-shot worker", async () => {
  const task = protectJob(file(), null, signal());
  await vi.waitFor(() => expect(mock.ports).toHaveLength(1));
  expect(mock.sent[0]!.password).toBeNull();
  expect(mock.sent[0]!.wasm).toBeUndefined();
  expect(JSON.stringify(mock.sent)).not.toContain("synthetic-private-name");
  reply({ ok: true, pages: 2 });
  await expect(task).resolves.toEqual({ pages: 2, bytes: undefined });
  expect(mock.ports[0]!.terminated).toBe(true);
  expect(mock.ports[0]!.onmessage).toBeNull();
  expect(mock.ports[0]!.onerror).toBeNull();
});
test("encryption sends a public resource copy, clears sender credentials and terminates on success", async () => {
  const task = protectJob(file(), "Synthetic-secret-123", signal());
  await vi.waitFor(() => expect(mock.ports).toHaveLength(1));
  expect(mock.sent[0]!.password).toBe("Synthetic-secret-123");
  expect(mock.payloads[0]!.password).toBe("");
  expect(new Uint8Array(mock.sent[0]!.wasm as ArrayBuffer)).toEqual(wasm);
  reply({ ok: true, pages: 2, bytes: new ArrayBuffer(12) });
  await expect(task).resolves.toHaveProperty("pages", 2);
  expect(mock.ports[0]!.terminated).toBe(true);
});
test.each([
  { ok: true, pages: 0 },
  { ok: true, pages: 201 },
  { ok: true, pages: 2 },
  { ok: true, pages: 2, bytes: new ArrayBuffer(0) },
])("rejects malformed output without publishing: %j", async (data) => {
  const task = protectJob(file(), "Synthetic-secret-123", signal());
  const rejected = expect(task).rejects.toMatchObject({ code: "VERIFY" });
  await vi.waitFor(() => expect(mock.ports).toHaveLength(1));
  reply(data);
  await rejected;
  expect(mock.ports[0]!.terminated).toBe(true);
});
test("raw worker diagnostics are replaced by allowlisted errors", async () => {
  const task = protectJob(file(), null, signal());
  const rejected = expect(task).rejects.toMatchObject({ code: "ENGINE" });
  await vi.waitFor(() => expect(mock.ports).toHaveLength(1));
  reply({ ok: false, code: "private-password-or-filename" });
  await rejected;
});
test.each(["constructor", "send", "error", "messageerror"])(
  "%s failure clears credentials and worker state",
  async (kind) => {
    mock.constructorFails = kind === "constructor";
    mock.sendFails = kind === "send";
    const task = protectJob(file(), "Synthetic-secret-123", signal());
    const rejected = expect(task).rejects.toMatchObject({ code: "ENGINE" });
    if (kind !== "constructor") {
      await vi.waitFor(() => expect(mock.ports).toHaveLength(1));
      if (kind === "error") mock.ports[0]!.onerror?.({} as ErrorEvent);
      if (kind === "messageerror")
        mock.ports[0]!.onmessageerror?.(new MessageEvent("messageerror"));
    }
    await rejected;
    if (kind !== "constructor") {
      expect(mock.ports[0]!.terminated).toBe(true);
      expect(mock.payloads[0]!.password).toBe("");
    }
  },
);
test("active cancellation and late responses cannot publish", async () => {
  const controller = new AbortController(),
    task = protectJob(file(), null, controller.signal);
  const rejected = expect(task).rejects.toMatchObject({ code: "CANCELLED" });
  await vi.waitFor(() => expect(mock.ports).toHaveLength(1));
  controller.abort();
  await rejected;
  expect(mock.ports[0]!.terminated).toBe(true);
  expect(mock.ports[0]!.onmessage).toBeNull();
});
test.each(["read", "engine"])(
  "cancellation while %s is stalled is immediate",
  async (stage) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );
    const input =
      stage === "read"
        ? ({
            size: 20,
            arrayBuffer: () => new Promise<ArrayBuffer>(() => {}),
          } as File)
        : file();
    const controller = new AbortController(),
      task = protectJob(input, "Synthetic-secret-123", controller.signal);
    const rejected = expect(task).rejects.toMatchObject({ code: "CANCELLED" });
    await Promise.resolve();
    controller.abort();
    await rejected;
    expect(mock.ports).toHaveLength(0);
  },
);
test("deadline releases a stalled private worker", async () => {
  vi.useFakeTimers();
  const task = protectJob(file(), null, signal());
  const rejected = expect(task).rejects.toMatchObject({ code: "TIMEOUT" });
  await vi.advanceTimersByTimeAsync(1);
  expect(mock.ports).toHaveLength(1);
  await vi.advanceTimersByTimeAsync(120000);
  await rejected;
  expect(mock.ports[0]!.terminated).toBe(true);
});
test("invalid inputs and insecure contexts never enter a worker", async () => {
  for (const size of [0, 100 * 1024 * 1024])
    await expect(
      protectJob({ size } as File, null, signal()),
    ).rejects.toBeDefined();
  const c = new AbortController();
  c.abort();
  await expect(protectJob(file(), null, c.signal)).rejects.toMatchObject({
    code: "CANCELLED",
  });
  vi.stubGlobal("isSecureContext", false);
  await expect(protectJob(file(), null, signal())).rejects.toMatchObject({
    code: "CONNECTION",
  });
  expect(mock.ports).toHaveLength(0);
});
