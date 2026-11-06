import { randomBytes } from "node:crypto";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import path from "node:path";

// Only a clean, never-used converter is retained. A claim consumes the slot.
export function createStandby({ root, run, broken }) {
  let current,
    paused = false,
    closed = false;
  async function removeReady(ready) {
    try {
      await run({ directory: ready.name, discardToken: ready.token }, () => {});
    } catch (error) {
      // Once a slot exists, a failed discard cannot prove it has disappeared.
      error.unsafe = true;
      broken(error);
      throw error;
    }
  }
  async function discard(slot) {
    if (!slot.ready) return;
    const ready = slot.ready;
    slot.ready = undefined;
    await removeReady(ready);
  }
  async function cancelSlot(slot) {
    slot.cancelled = true;
    if (slot.directory && !slot.finished)
      await writeFile(path.join(slot.directory, "cancel"), "cancel");
  }
  function clean(slot) {
    return (slot.cleanup ||= (async () => {
      await discard(slot);
      if (slot.directory)
        await rm(slot.directory, { recursive: true, force: true });
    })());
  }
  function ensure() {
    if (closed || paused || current) return;
    const slot = { cancelled: false, token: randomBytes(16).toString("hex") };
    current = slot;
    slot.promise = (async () => {
      try {
        slot.directory = await mkdtemp(path.join(root, "_standby-"));
        if (slot.cancelled) await cancelSlot(slot);
        await run(
          { directory: slot.directory, warmToken: slot.token },
          (value) => {
            if (value.standby) {
              if (
                value.standby.token !== slot.token ||
                !/^smartpdf-word-[a-f0-9]{32}$/.test(value.standby.name)
              )
                throw Error("Invalid converter handoff");
              slot.ready = value.standby;
            }
          },
        );
      } catch (error) {
        slot.error = error;
        if (error.unsafe) broken(error);
      } finally {
        slot.finished = true;
      }
    })().catch((error) => {
      slot.error = error;
      broken(error);
    });
  }
  return {
    ensure,
    async pause() {
      paused = true;
      const slot = current;
      if (!slot) return;
      await cancelSlot(slot);
      await slot.promise;
      await clean(slot);
      if (current === slot) current = undefined;
      if (slot.error?.unsafe) throw slot.error;
    },
    resume() {
      paused = false;
      ensure();
    },
    ready: () =>
      !!current?.ready &&
      !current?.claimed &&
      !current?.cancelled &&
      !current?.error,
    async release(ready) {
      if (ready) await removeReady(ready);
    },
    async take(job) {
      const slot = current;
      if (!slot || slot.claimed) return;
      slot.claimed = true;
      job.warming = slot;
      try {
        if (
          job.options?.revisionView &&
          job.options.revisionView !== "unchanged"
        )
          await cancelSlot(slot);
        await slot.promise;
        if (current === slot) current = undefined;
        if (slot.error) {
          await discard(slot);
          throw slot.error;
        }
        if (slot.cancelled || ["cancelled", "expired"].includes(job.state)) {
          await discard(slot);
          return;
        }
        const ready = slot.ready;
        slot.ready = undefined;
        return ready;
      } finally {
        delete job.warming;
        await clean(slot);
      }
    },
    async cancel(job) {
      if (job.warming) await cancelSlot(job.warming);
    },
    async close() {
      closed = true;
      const slot = current;
      current = undefined;
      if (slot) {
        await cancelSlot(slot);
        await slot.promise;
        await clean(slot);
      }
    },
  };
}
