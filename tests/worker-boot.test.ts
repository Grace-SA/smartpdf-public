import { afterEach, expect, test, vi } from "vitest";
import { waitForBoot } from "../src/platform/worker-boot";

afterEach(() => vi.useRealTimers());
const port = () => new EventTarget() as unknown as Worker;
test("boot waits for the actual ready packet and clears its deadline", async () => {
  vi.useFakeTimers();
  const worker = port();
  let complete = false;
  const pending = waitForBoot(worker, (data) => data?.ready === true).then(
    () => {
      complete = true;
    },
  );
  worker.dispatchEvent(
    new MessageEvent("message", { data: { unrelated: true } }),
  );
  await Promise.resolve();
  expect(complete).toBe(false);
  worker.dispatchEvent(new MessageEvent("message", { data: { ready: true } }));
  await pending;
  expect(complete).toBe(true);
  expect(vi.getTimerCount()).toBe(0);
});
test("a worker that never boots fails at the existing 15-second deadline", async () => {
  vi.useFakeTimers();
  const pending = expect(waitForBoot(port(), () => false)).rejects.toThrow(
    "RESOURCE_LOAD_FAILED",
  );
  await vi.advanceTimersByTimeAsync(15000);
  await pending;
  expect(vi.getTimerCount()).toBe(0);
});
test("boot error is reported and its deadline is cleared", async () => {
  vi.useFakeTimers();
  const worker = port();
  const pending = expect(waitForBoot(worker, () => false)).rejects.toThrow(
    "RESOURCE_LOAD_FAILED",
  );
  const error = new Event("error", { cancelable: true });
  worker.dispatchEvent(error);
  await pending;
  expect(error.defaultPrevented).toBe(true);
  expect(vi.getTimerCount()).toBe(0);
});
for (const alreadyAborted of [false, true])
  test(`boot cancellation cleans up (already aborted: ${alreadyAborted})`, async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    if (alreadyAborted) controller.abort();
    const pending = expect(
      waitForBoot(port(), () => false, controller.signal),
    ).rejects.toMatchObject({ code: "CANCELLED" });
    controller.abort();
    await pending;
    expect(vi.getTimerCount()).toBe(0);
  });
