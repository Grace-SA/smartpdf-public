import { afterEach, expect, it, vi } from "vitest";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import type { AddressInfo } from "node:net";
import { createWordService } from "../server/word/service.mjs";

const hooks = vi.hoisted(() => ({
  cancel: undefined as undefined | (() => Promise<void>),
  remove: undefined as undefined | (() => Promise<void>),
  directories: [] as string[],
}));
vi.mock("node:fs/promises", async (original) => {
  const fs = await original<typeof import("node:fs/promises")>();
  return {
    ...fs,
    writeFile: async (...args: Parameters<typeof fs.writeFile>) => {
      if (String(args[0]).endsWith(path.sep + "cancel")) await hooks.cancel?.();
      return fs.writeFile(...args);
    },
    rm: async (...args: Parameters<typeof fs.rm>) => {
      if (/^[a-f0-9-]{36}$/.test(path.basename(String(args[0])))) {
        hooks.directories.push(String(args[0]));
        await hooks.remove?.();
      }
      return fs.rm(...args);
    },
  };
});
const deferred = () => {
  let resolve!: () => void;
  const promise = new Promise<void>((r) => {
    resolve = r;
  });
  return { promise, resolve };
};
afterEach(() => {
  hooks.cancel = undefined;
  hooks.remove = undefined;
  hooks.directories = [];
});

it("waits for the cancellation marker and joins concurrent directory cleanup", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "office-cleanup-synthetic-"));
  const entered = deferred(),
    finish = deferred(),
    writing = deferred(),
    written = deferred(),
    removing = deferred(),
    removed = deferred();
  const service = await createWordService({
    root,
    origin: "http://127.0.0.1:4240",
    execute: async () => {
      entered.resolve();
      await finish.promise;
    },
    validate: async () => ({ pages: 1 }),
  });
  try {
    await new Promise<void>((r) => service.server.listen(0, "127.0.0.1", r));
    const url = `http://127.0.0.1:${(service.server.address() as AddressInfo).port}/api/word`;
    const session = await fetch(url + "/session");
    const cookie = session.headers.get("set-cookie")!.split(";")[0]!;
    const api = (p: string, method = "GET", body?: string) =>
      fetch(url + p, {
        method,
        body,
        headers: {
          origin: "http://127.0.0.1:4240",
          cookie,
          "Content-Type":
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
      });
    const job = await (await api("/jobs", "POST")).json();
    await api(`/jobs/${job.id}/input`, "PUT", "synthetic");
    await entered.promise;
    hooks.cancel = async () => {
      writing.resolve();
      await written.promise;
    };
    hooks.remove = async () => {
      removing.resolve();
      await removed.promise;
    };
    const first = api(`/jobs/${job.id}`, "DELETE");
    await writing.promise;
    finish.resolve();
    await vi.waitFor(() =>
      expect(service.jobs.get(job.id)!.state).toBe("cancelled"),
    );
    const second = api(`/jobs/${job.id}`, "DELETE");
    await new Promise((r) => setTimeout(r, 30));
    expect(hooks.directories).toHaveLength(0);
    written.resolve();
    await removing.promise;
    await new Promise((r) => setTimeout(r, 30));
    expect(hooks.directories).toHaveLength(1);
    removed.resolve();
    await Promise.all([first, second]);
    await vi.waitFor(async () =>
      expect((await (await api(`/jobs/${job.id}`)).json()).cleanupPending).toBe(
        false,
      ),
    );
    expect((await api("/health")).status).toBe(200);
    expect((await api(`/jobs/${job.id}/result`)).status).not.toBe(200);
  } finally {
    written.resolve();
    removed.resolve();
    finish.resolve();
    await service.close();
    await rm(root, { recursive: true, force: true });
  }
});
