import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type WorkerReply =
  | { kind: "prepared"; ok: boolean; message?: string }
  | {
      kind: "compressed";
      id: number;
      ok: boolean;
      bytes?: ArrayBuffer;
      message?: string;
    };

type MockWorker = {
  onmessage: ((event: MessageEvent<WorkerReply>) => void) | null;
  onerror: ((event: ErrorEvent) => void) | null;
  terminated: boolean;
  postMessage: (message: { kind: string; id?: number }) => void;
  terminate: () => void;
};

const mocks = vi.hoisted(() => ({ instances: [] as MockWorker[] }));

vi.mock("../src/compress/compress.worker?worker", () => ({
  default: class {
    onmessage: MockWorker["onmessage"] = null;
    onerror: MockWorker["onerror"] = null;
    terminated = false;

    constructor() {
      mocks.instances.push(this);
    }

    postMessage(message: { kind: string; id?: number }) {
      if (message.kind === "prepare")
        queueMicrotask(() =>
          this.onmessage?.(
            new MessageEvent("message", {
              data: { kind: "prepared", ok: true },
            }),
          ),
        );
    }

    terminate() {
      this.terminated = true;
    }
  },
}));

import {
  compressPdf,
  disposeCompress,
  prepareCompress,
} from "../src/compress/service";

describe("compression worker lifecycle", () => {
  beforeEach(() => {
    disposeCompress();
    mocks.instances.length = 0;
    vi.stubGlobal("window", { location: { origin: "http://localhost" } });
  });

  afterEach(() => {
    disposeCompress();
    vi.unstubAllGlobals();
  });

  it("removes preparation listeners and releases the persistent worker", async () => {
    await prepareCompress(new AbortController().signal);
    const worker = mocks.instances[0]!;
    expect(worker.onmessage).toBeNull();
    expect(worker.onerror).toBeNull();

    disposeCompress();
    expect(worker.terminated).toBe(true);
  });

  it("does not start a worker after tool initialization was cancelled", async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(prepareCompress(controller.signal)).rejects.toThrow("Aborted");
    expect(mocks.instances).toHaveLength(0);
  });

  it("discards a failed engine and prepares a fresh worker for retry", async () => {
    const first = compressPdf(
      new File([new Uint8Array([1, 2, 3])], "input.pdf"),
      "recommended",
      new AbortController().signal,
      () => {},
    );
    await vi.waitFor(() => expect(mocks.instances).toHaveLength(1));
    const failed = mocks.instances[0]!;
    await vi.waitFor(() => expect(failed.onmessage).not.toBeNull());
    failed.onmessage?.(
      new MessageEvent("message", {
        data: {
          kind: "compressed",
          id: 1,
          ok: false,
          message: "failed safely",
        },
      }),
    );
    await expect(first).rejects.toThrow("failed safely");
    expect(failed.terminated).toBe(true);
    expect(failed.onmessage).toBeNull();
    expect(failed.onerror).toBeNull();

    await prepareCompress(new AbortController().signal);
    expect(mocks.instances).toHaveLength(2);
    expect(mocks.instances[1]!.terminated).toBe(false);
  });
});
