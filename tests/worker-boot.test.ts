import { afterEach, expect, test, vi } from "vitest";
import { waitForBoot } from "../src/platform/worker-boot";

afterEach(() => vi.useRealTimers());
const port = () =>
  Object.assign(new EventTarget(), { terminate: vi.fn() }) as unknown as Worker;
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
    const start = vi.fn();
    if (alreadyAborted) controller.abort();
    const pending = expect(
      waitForBoot(port(), () => false, controller.signal, start),
    ).rejects.toMatchObject({ code: "CANCELLED" });
    controller.abort();
    await pending;
    expect(vi.getTimerCount()).toBe(0);
    expect(start).toHaveBeenCalledTimes(alreadyAborted ? 0 : 1);
  });

test("request listeners are installed before a synchronous acknowledgement", async () => {
  vi.useFakeTimers();
  const worker = port();
  await waitForBoot(
    worker,
    (data) => data?.ready === true,
    undefined,
    () => {
      worker.dispatchEvent(
        new MessageEvent("message", { data: { ready: true } }),
      );
    },
  );
  expect(vi.getTimerCount()).toBe(0);
});

test("cancellation terminates synchronously and consumes only a failed worker's late error", async () => {
  const worker = port();
  const controller = new AbortController();
  const pending = expect(
    waitForBoot(worker, () => false, controller.signal),
  ).rejects.toMatchObject({ code: "CANCELLED" });
  controller.abort();
  expect(worker.terminate).toHaveBeenCalledTimes(1);
  const late = new Event("error", { cancelable: true });
  worker.dispatchEvent(late);
  expect(late.defaultPrevented).toBe(true);
  await pending;
  const live = port();
  const ready = waitForBoot(live, (data) => data?.ready === true);
  live.dispatchEvent(new MessageEvent("message", { data: { ready: true } }));
  await ready;
  expect(live.terminate).not.toHaveBeenCalled();
  const unexpected = new Event("error", { cancelable: true });
  live.dispatchEvent(unexpected);
  expect(unexpected.defaultPrevented).toBe(false);
});

test("a synchronous request failure clears listeners and its deadline", async () => {
  vi.useFakeTimers();
  const worker = port();
  const remove = vi.spyOn(worker, "removeEventListener");
  await expect(
    waitForBoot(
      worker,
      () => false,
      undefined,
      () => {
        throw new Error("SYNTHETIC_SEND_FAILURE");
      },
    ),
  ).rejects.toThrow("SYNTHETIC_SEND_FAILURE");
  expect(vi.getTimerCount()).toBe(0);
  expect(remove.mock.calls.map(([type]) => type)).toEqual(["message", "error"]);
});
