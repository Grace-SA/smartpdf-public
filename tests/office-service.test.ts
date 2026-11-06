import { afterEach, expect, it } from "vitest";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { AddressInfo } from "node:net";
import type { Task } from "../server/word/service.mjs";
import { createOfficeServices } from "../server/office/service.mjs";
import { PDFDocument } from "pdf-lib";
const clean: (() => Promise<void>)[] = [];
afterEach(async () => {
  for (const fn of clean.splice(0)) await fn();
});
async function setup(
  word: (job: Task) => Promise<void>,
  ppt: (job: Task) => Promise<void>,
) {
  const root = await mkdtemp(path.join(os.tmpdir(), "office-synthetic-"));
  const origin = "http://127.0.0.1:4240";
  const services = await createOfficeServices({
    word: {
      root: path.join(root, "word"),
      origin,
      execute: word,
      enableExcel: true,
    },
    ppt: { root: path.join(root, "ppt"), origin, execute: ppt },
  });
  clean.push(async () => {
    await services.close();
    await rm(root, { recursive: true, force: true });
  });
  const api: Record<
    string,
    (route: string, method?: string, body?: string) => Promise<Response>
  > = {};
  for (const kind of ["word", "ppt", "excel"] as const) {
    const service = services[kind === "excel" ? "word" : kind];
    if (kind !== "excel")
      await new Promise<void>((r) => service.server.listen(0, "127.0.0.1", r));
    const url = `http://127.0.0.1:${(service.server.address() as AddressInfo).port}/api/${kind}`;
    const session = await fetch(url + "/session");
    const cookie = session.headers.get("set-cookie")!.split(";")[0]!;
    api[kind] = (route, method = "GET", body) =>
      fetch(url + route, {
        method,
        body,
        headers: {
          "X-Excel-Options": JSON.stringify({
            sheets: [0],
            orientation: "keep",
            paper: "keep",
            scale: "keep",
          }),
          origin,
          cookie,
          "Content-Type":
            kind === "excel"
              ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              : kind === "ppt"
                ? "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                : "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
      });
  }
  async function job(kind: string) {
    const value = await (await api[kind]!("/jobs", "POST")).json();
    expect(
      (
        await api[kind]!(
          `/jobs/${value.id}/input`,
          "PUT",
          "original synthetic input",
        )
      ).status,
    ).toBe(202);
    return value.id;
  }
  async function wait(kind: string, id: string, state: string) {
    for (let i = 0; i < 100; i++) {
      const j = await (await api[kind]!(`/jobs/${id}`)).json();
      if (j.state === state && !j.cleanupPending) return j;
      if (j.state === "failed" && state !== "failed")
        throw Error(JSON.stringify(j));
      await new Promise((r) => setTimeout(r, 100));
    }
    throw Error("state not reached");
  }
  return { api, job, wait };
}
async function output(job: Task) {
  const pdf = await PDFDocument.create();
  pdf.addPage([960, 540]);
  await writeFile(path.join(job.directory, "output.pdf"), await pdf.save());
  await writeFile(
    path.join(job.directory, "expected.json"),
    JSON.stringify({ visible: 1, width: 960, height: 540 }),
  );
}
it.each(["word", "excel"])(
  "queues %s and PPT behind one engine and cancels waiting PPT without executing",
  async (kind) => {
    let finish!: () => void, started!: () => void;
    const pending = new Promise<void>((r) => {
      finish = r;
    });
    const entered = new Promise<void>((r) => {
      started = r;
    });
    let live = 0,
      peak = 0,
      pptCalls = 0;
    const s = await setup(
      async (j) => {
        peak = Math.max(peak, ++live);
        started();
        await pending;
        await output(j);
        live--;
      },
      async (j) => {
        pptCalls++;
        peak = Math.max(peak, ++live);
        await output(j);
        live--;
      },
    );
    const word = await s.job(kind);
    await entered;
    const ppt = await s.job("ppt");
    expect((await (await s.api.ppt!(`/jobs/${ppt}`)).json()).state).toBe(
      "queued",
    );
    expect(pptCalls).toBe(0);
    await s.api.ppt!(`/jobs/${ppt}`, "DELETE");
    await s.wait("ppt", ppt, "cancelled");
    finish();
    await s.wait(kind, word, "succeeded");
    const next = await s.job("ppt");
    await s.wait("ppt", next, "succeeded");
    expect(peak).toBe(1);
    expect(pptCalls).toBe(1);
  },
);
it("marks both API health and admission unavailable after uncertain cleanup", async () => {
  const s = await setup(async () => {
    throw Object.assign(Error("synthetic cleanup uncertainty"), {
      unsafe: true,
    });
  }, output);
  const id = await s.job("word");
  await s.wait("word", id, "failed");
  expect((await s.api.word!("/health")).status).toBe(503);
  expect((await s.api.ppt!("/health")).status).toBe(503);
  expect((await s.api.ppt!("/jobs", "POST")).status).toBe(503);
});
