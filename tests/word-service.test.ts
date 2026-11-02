import { afterEach, describe, expect, it } from "vitest";
import { mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import type { AddressInfo } from "node:net";
import { PDFDocument } from "pdf-lib";
import {
  createWordService,
  checkPdf,
  type Task,
} from "../server/word/service.mjs";

const origin = "http://127.0.0.1:4240";
const type =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const cleanup: (() => Promise<void>)[] = [];
afterEach(async () => {
  await Promise.all(cleanup.splice(0).map((fn) => fn()));
});
async function setup(
  execute?: (
    job: Task,
    update: (value: { state?: string }) => void,
  ) => Promise<void>,
  clock?: () => number,
) {
  const root = await mkdtemp(path.join(tmpdir(), "smartpdf-word-test-"));
  const pdf = await PDFDocument.create();
  pdf.addPage();
  const output = await pdf.save();
  const service = await createWordService({
    root,
    origin,
    now: clock,
    execute:
      execute ||
      (async (job) => {
        await writeFile(path.join(job.directory, "output.pdf"), output);
      }),
  });
  await new Promise<void>((resolve) =>
    service.server.listen(0, "127.0.0.1", resolve),
  );
  const base = `http://127.0.0.1:${(service.server.address() as AddressInfo).port}/api/word`;
  cleanup.push(async () => {
    await service.close();
    await rm(root, { recursive: true, force: true });
  });
  async function session() {
    const r = await fetch(base + "/session");
    return r.headers.get("set-cookie")!.split(";")[0]!;
  }
  async function api(
    cookie: string,
    suffix: string,
    method = "GET",
    body?: string,
  ) {
    return fetch(base + suffix, {
      method,
      headers: {
        Cookie: cookie,
        Origin: origin,
        ...(body !== undefined ? { "Content-Type": type } : {}),
      },
      body,
    });
  }
  const cookie = await session();
  async function job() {
    return (await (await api(cookie, "/jobs", "POST")).json()).id as string;
  }
  async function wait(id: string, state: string) {
    for (let n = 0; n < 100; n++) {
      const value = await (await api(cookie, "/jobs/" + id)).json();
      if (value.state === state) return value;
      await new Promise((resolve) => setTimeout(resolve, 20));
    }
    throw new Error("State not reached: " + state);
  }
  return { root, service, base, cookie, session, api, job, wait };
}
describe("Word cloud task isolation and lifecycle", () => {
  it("releases slots held by clients that never start uploading", async () => {
    let time = Date.now();
    const t = await setup(undefined, () => time);
    for (let n = 0; n < 3; n++)
      expect((await t.api(await t.session(), "/jobs", "POST")).status).toBe(
        201,
      );
    expect((await t.api(await t.session(), "/jobs", "POST")).status).toBe(429);
    time += 61000;
    await t.service.sweep();
    expect(await readdir(t.root)).toEqual([]);
    expect((await t.api(t.cookie, "/jobs", "POST")).status).toBe(201);
  });
  it("requires own-origin mutations and a session; hides another session's task", async () => {
    const t = await setup();
    const id = await t.job();
    expect((await fetch(t.base + "/jobs", { method: "POST" })).status).toBe(
      403,
    );
    expect(
      (
        await fetch(t.base + "/jobs", {
          method: "POST",
          headers: { Origin: origin },
        })
      ).status,
    ).toBe(401);
    const other = await t.session();
    for (const suffix of ["", "/result", "/input"]) {
      expect(
        (
          await t.api(
            other,
            `/jobs/${id}${suffix}`,
            suffix === "/input" ? "PUT" : "GET",
            suffix === "/input" ? "x" : undefined,
          )
        ).status,
      ).toBe(404);
    }
    expect((await t.api(other, `/jobs/${id}`, "DELETE")).status).toBe(404);
  });
  it("validates output before serving and deletes input and result", async () => {
    const t = await setup();
    const id = await t.job();
    expect((await t.api(t.cookie, `/jobs/${id}/result`)).status).toBe(409);
    expect(
      (
        await t.api(
          t.cookie,
          `/jobs/${id}/input`,
          "PUT",
          "synthetic-placeholder",
        )
      ).status,
    ).toBe(202);
    const value = await t.wait(id, "succeeded");
    expect(value.pages).toBe(1);
    expect(await readdir(path.join(t.root, id))).toEqual(["output.pdf"]);
    const result = await t.api(t.cookie, `/jobs/${id}/result`);
    expect(result.headers.get("cache-control")).toBe("no-store");
    expect((await result.text()).startsWith("%PDF-")).toBe(true);
    await t.api(t.cookie, `/jobs/${id}`, "DELETE");
    expect((await t.api(t.cookie, `/jobs/${id}/result`)).status).toBe(409);
    expect(await readdir(t.root)).toEqual([]);
  });
  it("rejects duplicate upload, bounds queued tasks and keeps cancellation final", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const t = await setup(async (job, update) => {
      update({ state: "converting" });
      await gate;
      await writeFile(path.join(job.directory, "output.pdf"), "late output");
    });
    const id = await t.job();
    await t.api(t.cookie, `/jobs/${id}/input`, "PUT", "synthetic");
    await t.wait(id, "converting");
    expect(
      (await t.api(t.cookie, `/jobs/${id}/input`, "PUT", "again")).status,
    ).toBe(409);
    expect((await t.api(t.cookie, "/jobs", "POST")).status).toBe(429);
    for (let n = 0; n < 2; n++)
      expect((await t.api(await t.session(), "/jobs", "POST")).status).toBe(
        201,
      );
    expect((await t.api(await t.session(), "/jobs", "POST")).status).toBe(429);
    await t.api(t.cookie, `/jobs/${id}`, "DELETE");
    expect(await readFile(path.join(t.root, id, "cancel"), "utf8")).toBe(
      "cancel",
    );
    release();
    for (let n = 0; n < 100 && (await readdir(t.root)).includes(id); n++)
      await new Promise((resolve) => setTimeout(resolve, 10));
    expect((await (await t.api(t.cookie, `/jobs/${id}`)).json()).state).toBe(
      "cancelled",
    );
    expect((await readdir(t.root)).includes(id)).toBe(false);
  });
  it("expires results and rejects invalid PDFs", async () => {
    let time = Date.now();
    const t = await setup(undefined, () => time);
    const id = await t.job();
    await t.api(t.cookie, `/jobs/${id}/input`, "PUT", "synthetic");
    await t.wait(id, "succeeded");
    time += 59 * 60000 + 30001;
    await t.service.sweep();
    expect((await t.api(t.cookie, `/jobs/${id}/result`)).status).toBe(404);
    expect(await readdir(t.root)).toEqual([]);
    const bad = path.join(t.root, "bad.pdf");
    await writeFile(bad, "%PDF-broken");
    await expect(checkPdf(bad)).rejects.toThrow();
  });
  it("refuses invalid input media types and unsigned sessions", async () => {
    const t = await setup();
    const id = await t.job();
    const forged = t.cookie.slice(0, -1) + (t.cookie.endsWith("0") ? "1" : "0");
    expect((await t.api(forged, `/jobs/${id}`)).status).toBe(401);
    expect(
      (
        await fetch(`${t.base}/jobs/${id}/input`, {
          method: "PUT",
          headers: {
            Origin: origin,
            Cookie: t.cookie,
            "Content-Type": "application/pdf",
          },
          body: "synthetic",
        })
      ).status,
    ).toBe(415);
    expect((await t.api(t.cookie, `/jobs/${id}/input`, "PUT", "")).status).toBe(
      400,
    );
    expect(await readdir(t.root)).toEqual([]);
  });
  it("never exposes invalid output and stops new work after uncertain container cleanup", async () => {
    const invalid = await setup(async (job) => {
      await writeFile(path.join(job.directory, "output.pdf"), "%PDF-broken");
    });
    const id = await invalid.job();
    await invalid.api(invalid.cookie, `/jobs/${id}/input`, "PUT", "synthetic");
    await invalid.wait(id, "failed");
    expect(
      (await invalid.api(invalid.cookie, `/jobs/${id}/result`)).status,
    ).toBe(409);
    const unsafe = await setup(async () => {
      throw Object.assign(new Error("cleanup"), { unsafe: true });
    });
    const other = await unsafe.job();
    await unsafe.api(unsafe.cookie, `/jobs/${other}/input`, "PUT", "synthetic");
    await unsafe.wait(other, "failed");
    expect((await unsafe.api(unsafe.cookie, "/jobs", "POST")).status).toBe(503);
  });
});
