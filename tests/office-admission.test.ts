import { expect, it } from "vitest";
import { createOfficeAdmission } from "../server/office/admission.mjs";

const signal = () => new AbortController().signal;
const deferred = () => {
  let resolve!: () => void;
  return {
    promise: new Promise<void>((r) => {
      resolve = r;
    }),
    resolve: () => resolve(),
  };
};

it("serializes Word/PPT admission and removes idle Word before admitting PPT", async () => {
  const clean = deferred();
  const events: string[] = [];
  const gate = createOfficeAdmission({
    pauseWord: async () => {
      events.push("discard-start");
      await clean.promise;
      events.push("discarded");
    },
    resumeWord: () => {
      events.push("prewarm");
    },
  });
  const word = await gate.acquire("word", signal());
  const pptPromise = gate.acquire("ppt", signal());
  const nextWord = gate.acquire("word", signal());
  expect(events).toEqual([]);
  await word();
  expect(events).toEqual(["discard-start"]);
  let admitted = false;
  void pptPromise.then(() => {
    admitted = true;
  });
  await Promise.resolve();
  expect(admitted).toBe(false);
  clean.resolve();
  const ppt = await pptPromise;
  expect(events).toEqual(["discard-start", "discarded"]);
  await ppt();
  const final = await nextWord;
  expect(events).toEqual(["discard-start", "discarded", "prewarm"]);
  await final();
  gate.close();
});

it("cancels a waiting task without execution and keeps another format moving", async () => {
  let pauses = 0;
  const gate = createOfficeAdmission({
    pauseWord: async () => {
      pauses++;
    },
    resumeWord: () => {},
  });
  const held = await gate.acquire("word", signal());
  const controller = new AbortController();
  const waiting = gate.acquire("ppt", controller.signal);
  const rejected = expect(waiting).rejects.toHaveProperty("name", "AbortError");
  controller.abort();
  await rejected;
  const next = gate.acquire("word", signal());
  await held();
  await (
    await next
  )();
  expect(pauses).toBe(0);
  gate.close();
});

it("finishes idle cleanup before honoring cancellation during admission", async () => {
  const clean = deferred();
  let completed = false;
  const gate = createOfficeAdmission({
    pauseWord: async () => {
      await clean.promise;
      completed = true;
    },
    resumeWord: () => {},
  });
  const controller = new AbortController();
  const ppt = gate.acquire("ppt", controller.signal);
  const rejected = expect(ppt).rejects.toHaveProperty("name", "AbortError");
  controller.abort();
  const word = gate.acquire("word", signal());
  let entered = false;
  void word.then(() => {
    entered = true;
  });
  await Promise.resolve();
  expect(entered).toBe(false);
  clean.resolve();
  await rejected;
  await (
    await word
  )();
  expect(completed).toBe(true);
  gate.close();
});

it("stops both formats after unsafe engine cleanup and rejects queued work", async () => {
  const gate = createOfficeAdmission({
    pauseWord: async () => {},
    resumeWord: () => {},
  });
  const held = await gate.acquire("ppt", signal());
  const word = gate.acquire("word", signal());
  const rejected = expect(word).rejects.toHaveProperty("unsafe", true);
  await held(false);
  await rejected;
  expect(gate.available()).toBe(false);
  await expect(gate.acquire("ppt", signal())).rejects.toHaveProperty(
    "unsafe",
    true,
  );
});

it("does not admit PPT or later Word after a failed idle discard", async () => {
  const failure = Error("discard");
  const gate = createOfficeAdmission({
    pauseWord: async () => {
      throw failure;
    },
    resumeWord: () => {},
  });
  await expect(gate.acquire("ppt", signal())).rejects.toHaveProperty(
    "unsafe",
    true,
  );
  expect(gate.available()).toBe(false);
  await expect(gate.acquire("word", signal())).rejects.toHaveProperty(
    "unsafe",
    true,
  );
});

it("does not prewarm between consecutive PPT tasks and closes queued work", async () => {
  let warms = 0;
  const gate = createOfficeAdmission({
    pauseWord: async () => {},
    resumeWord: () => {
      warms++;
    },
  });
  const first = await gate.acquire("ppt", signal());
  const second = gate.acquire("ppt", signal());
  await first();
  const release = await second;
  expect(warms).toBe(0);
  const pending = gate.acquire("word", signal());
  const rejected = expect(pending).rejects.toHaveProperty("name", "AbortError");
  gate.close();
  await rejected;
  await release();
  expect(warms).toBe(0);
});
