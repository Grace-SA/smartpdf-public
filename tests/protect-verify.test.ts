import { afterEach, beforeEach, expect, it, vi } from "vitest";
const mock = vi.hoisted(() => ({
  getDocument: vi.fn(),
  destroyed: vi.fn(),
  boot: vi.fn(),
  ports: [] as { terminated: boolean }[],
}));
vi.mock("pdfjs-dist/legacy/build/pdf.mjs", () => ({
  PDFWorker: class {
    destroy() {
      mock.destroyed();
    }
  },
  getDocument: mock.getDocument,
}));
vi.mock("../src/platform/worker-boot", () => ({ waitForBoot: mock.boot }));
import { verifyPasswords } from "../src/protect/verify";
beforeEach(() => {
  vi.resetAllMocks();
  mock.ports.length = 0;
  mock.boot.mockResolvedValue(undefined);
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("/* public synthetic worker */")),
  );
  vi.stubGlobal(
    "Worker",
    class {
      terminated = false;
      constructor() {
        mock.ports.push(this);
      }
      terminate() {
        this.terminated = true;
      }
    },
  );
});
afterEach(() => vi.unstubAllGlobals());
it("M11 reader initialization failure releases its worker", async () => {
  mock.getDocument.mockImplementation(() => {
    throw Error("synthetic allocation failure");
  });
  await expect(
    verifyPasswords(
      new ArrayBuffer(1),
      "Synthetic-M11-Only!",
      1,
      new AbortController().signal,
    ),
  ).rejects.toMatchObject({ code: "VERIFY" });
  expect(mock.ports[0]!.terminated).toBe(true);
  expect(mock.destroyed).toHaveBeenCalledOnce();
});
it("M11 reader boot failure releases its port", async () => {
  mock.boot.mockRejectedValue(Error("synthetic boot failure"));
  await expect(
    verifyPasswords(
      new ArrayBuffer(1),
      "Synthetic-M11-Only!",
      1,
      new AbortController().signal,
    ),
  ).rejects.toMatchObject({ code: "VERIFY" });
  expect(mock.ports[0]!.terminated).toBe(true);
  expect(mock.getDocument).not.toHaveBeenCalled();
});
it("M11 refuses a reader that opens without a password", async () => {
  mock.getDocument.mockReturnValue({
    promise: Promise.resolve({ numPages: 1 }),
    destroy: vi.fn().mockResolvedValue(undefined),
  });
  await expect(
    verifyPasswords(
      new ArrayBuffer(1),
      "Synthetic-M11-Only!",
      1,
      new AbortController().signal,
    ),
  ).rejects.toMatchObject({ code: "VERIFY" });
  expect(mock.ports[0]!.terminated).toBe(true);
});
it("M11 validates three password states and disposes every reader", async () => {
  const destroy = vi.fn().mockResolvedValue(undefined);
  mock.getDocument.mockImplementation(({ password }: { password: string }) => ({
    promise:
      password === "Synthetic-M11-Only!"
        ? Promise.resolve({ numPages: 1 })
        : Promise.reject(
            Object.assign(new Error("synthetic"), {
              name: "PasswordException",
            }),
          ),
    destroy,
  }));
  await verifyPasswords(
    new ArrayBuffer(1),
    "Synthetic-M11-Only!",
    1,
    new AbortController().signal,
  );
  expect(mock.ports).toHaveLength(3);
  expect(mock.ports.every((p) => p.terminated)).toBe(true);
  expect(destroy).toHaveBeenCalledTimes(3);
});
it("M11 cancellation releases a stalled independent reader", async () => {
  const destroy = vi.fn().mockResolvedValue(undefined);
  mock.getDocument.mockReturnValue({ promise: new Promise(() => {}), destroy });
  const controller = new AbortController();
  const task = verifyPasswords(
    new ArrayBuffer(1),
    "Synthetic-M11-Only!",
    1,
    controller.signal,
  );
  const rejected = expect(task).rejects.toMatchObject({ code: "CANCELLED" });
  await vi.waitFor(() => expect(mock.getDocument).toHaveBeenCalled());
  controller.abort();
  await rejected;
  expect(mock.ports[0]!.terminated).toBe(true);
  expect(destroy).toHaveBeenCalledOnce();
});
it("M11 cancellation does not wait for a stuck reader cleanup acknowledgement", async () => {
  const destroy = vi.fn(() => new Promise<void>(() => {}));
  mock.getDocument.mockReturnValue({ promise: new Promise(() => {}), destroy });
  const controller = new AbortController();
  const task = verifyPasswords(
    new ArrayBuffer(1),
    "Synthetic-M11-Only!",
    1,
    controller.signal,
  );
  const rejected = expect(task).rejects.toMatchObject({ code: "CANCELLED" });
  await vi.waitFor(() => expect(mock.getDocument).toHaveBeenCalled());
  controller.abort();
  await rejected;
  expect(mock.ports[0]!.terminated).toBe(true);
  expect(destroy).toHaveBeenCalledOnce();
});
