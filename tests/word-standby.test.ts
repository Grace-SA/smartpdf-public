import { it, expect } from "vitest";
import { mkdtemp, rm, readFile, readdir } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createStandby } from "../server/word/standby.mjs";
it("stops admission when a clean converter cannot be discarded", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "word-standby-synthetic-"));
  const failure = new Error("discard process unavailable");
  const broken: unknown[] = [];
  const pool = createStandby({
    root,
    broken: (error) => broken.push(error),
    run: async () => {
      throw failure;
    },
  });
  try {
    await expect(
      pool.release({
        name: "smartpdf-word-" + "a".repeat(32),
        token: "b".repeat(32),
      }),
    ).rejects.toBe(failure);
    expect(broken).toEqual([failure]);
    expect(failure).toHaveProperty("unsafe", true);
  } finally {
    await pool.close();
    await rm(root, { recursive: true, force: true });
  }
});
it("fails promptly after verified startup failure instead of booting twice", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "word-standby-synthetic-"));
  const failure = Object.assign(new Error("startup"), {
    code: "ENGINE_STARTUP_FAILED",
  });
  let broken = 0;
  const pool = createStandby({
    root,
    broken: () => broken++,
    run: async () => {
      throw failure;
    },
  });
  try {
    pool.ensure();
    await expect(pool.take({ state: "queued" })).rejects.toBe(failure);
    expect(broken).toBe(0);
  } finally {
    await pool.close();
    await rm(root, { recursive: true, force: true });
  }
});
it("preheats one clean slot and hands it off only once", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "word-standby-synthetic-"));
  let warm = 0,
    discard = 0;
  const pool = createStandby({
    root,
    broken: () => {
      throw Error("unexpected");
    },
    run: async (job, update) => {
      if (job.warmToken) {
        warm++;
        update({
          standby: {
            name: "smartpdf-word-" + "a".repeat(32),
            token: job.warmToken,
          },
        });
      } else discard++;
    },
  });
  try {
    pool.ensure();
    pool.ensure();
    const values = await Promise.all([
      pool.take({ state: "queued" }),
      pool.take({ state: "queued" }),
    ]);
    expect(warm).toBe(1);
    expect(values.filter(Boolean)).toHaveLength(1);
    expect(await pool.take({ state: "queued" })).toBeUndefined();
    await pool.close();
    expect(discard).toBe(0);
    expect(await readdir(root)).toEqual([]);
  } finally {
    await pool.close();
    await rm(root, { recursive: true, force: true });
  }
});
it("discards an unused clean slot for revision preparation and on shutdown", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "word-standby-synthetic-"));
  const discarded: string[] = [];
  const pool = createStandby({
    root,
    broken: () => {},
    run: async (job, update) => {
      if (job.warmToken)
        update({
          standby: {
            name: "smartpdf-word-" + "b".repeat(32),
            token: job.warmToken,
          },
        });
      else if (job.discardToken) discarded.push(job.discardToken);
    },
  });
  try {
    pool.ensure();
    expect(
      await pool.take({ state: "queued", options: { revisionView: "final" } }),
    ).toBeUndefined();
    expect(discarded).toHaveLength(1);
    pool.ensure();
    await pool.close();
    expect(discarded).toHaveLength(2);
    expect(await readdir(root)).toEqual([]);
  } finally {
    await pool.close();
    await rm(root, { recursive: true, force: true });
  }
});
it("cancels a warming task through a local control file before handoff", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "word-standby-synthetic-"));
  let finish!: () => void, started!: () => void;
  let directory = "";
  const ready = new Promise<void>((resolve) => (started = resolve));
  const pool = createStandby({
    root,
    broken: () => {},
    run: async (job) => {
      directory = job.directory;
      started();
      await new Promise<void>((resolve) => (finish = resolve));
    },
  });
  try {
    pool.ensure();
    await ready;
    const job = { state: "queued" };
    const pending = pool.take(job);
    job.state = "cancelled";
    await pool.cancel(job);
    expect(await readFile(path.join(directory, "cancel"), "utf8")).toBe(
      "cancel",
    );
    finish();
    expect(await pending).toBeUndefined();
    await pool.close();
  } finally {
    finish?.();
    await pool.close();
    await rm(root, { recursive: true, force: true });
  }
});
it("reports uncertain cleanup instead of handing off an unverified converter", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "word-standby-synthetic-"));
  const failure = Object.assign(new Error("cleanup"), { unsafe: true });
  const broken: unknown[] = [];
  const pool = createStandby({
    root,
    broken: (error) => broken.push(error),
    run: async () => {
      throw failure;
    },
  });
  try {
    pool.ensure();
    await expect(pool.take({ state: "queued" })).rejects.toBe(failure);
    expect(broken).toEqual([failure]);
  } finally {
    await pool.close();
    await rm(root, { recursive: true, force: true });
  }
});
