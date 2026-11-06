import { afterEach, expect, it } from "vitest";
import { mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import type { AddressInfo } from "node:net";
import { request } from "node:http";
import { PDFDocument, PDFName, PDFString } from "pdf-lib";
import { createPptService } from "../server/ppt/service.mjs";
import { checkPdf, type Task } from "../server/word/service.mjs";
const cleanup: (() => Promise<void>)[] = [];
const origin = "http://127.0.0.1:4280";
const mime =
  "application/vnd.openxmlformats-officedocument.presentationml.presentation";
afterEach(async () => {
  for (const fn of cleanup.splice(0)) await fn();
});

async function setup(execute?: (job: Task) => Promise<void>) {
  const root = await mkdtemp(path.join(tmpdir(), "smartpdf-ppt-test-"));
  const service = await createPptService({
    root,
    origin,
    execute:
      execute ||
      (async (job) => {
        expect(
          await readFile(path.join(job.directory, "input.pptx"), "utf8"),
        ).toBe("synthetic-input");
        const pdf = await PDFDocument.create();
        pdf.addPage([960, 540]);
        await writeFile(
          path.join(job.directory, "output.pdf"),
          await pdf.save(),
        );
        await writeFile(
          path.join(job.directory, "expected.json"),
          JSON.stringify({ visible: 1, width: 960, height: 540 }),
        );
      }),
  });
  await new Promise<void>((resolve) =>
    service.server.listen(0, "127.0.0.1", resolve),
  );
  cleanup.push(async () => {
    await service.close();
    await rm(root, { recursive: true, force: true });
  });
  const url = `http://127.0.0.1:${(service.server.address() as AddressInfo).port}/api/ppt`;
  const session = await fetch(url + "/session");
  const cookie = session.headers.get("set-cookie")!.split(";")[0]!;
  const api = (
    suffix: string,
    method = "GET",
    body?: string,
    owner = cookie,
    contentType = mime,
  ) =>
    fetch(url + suffix, {
      method,
      headers: { origin, cookie: owner, "Content-Type": contentType },
      body,
    });
  async function wait(id: string, state: string) {
    for (let i = 0; i < 100; i++) {
      const value = await (await api(`/jobs/${id}`)).json();
      if (value.state === state && !value.cleanupPending) return value;
      await new Promise((resolve) => setTimeout(resolve, 20));
    }
    throw Error("task did not finish");
  }
  return { service, api, cookie, url, wait };
}

it("namespaces cookies and endpoints and requires own-origin mutations", async () => {
  const s = await setup();
  expect((await (await s.api("/session")).json()).maxBytes).toBe(
    60 * 1024 ** 2,
  );
  expect(s.cookie).toMatch(/^ppt_session=/);
  expect(
    (
      await fetch(s.url + "/jobs", {
        method: "POST",
        headers: { cookie: s.cookie },
      })
    ).status,
  ).toBe(403);
  expect(
    (await fetch(s.url.replace("/ppt", "/word") + "/session")).status,
  ).toBe(404);
  expect(
    (await s.api("/jobs", "POST", undefined, "word_session=invalid")).status,
  ).toBe(401);
});

it("accepts a 31 MiB upload and rejects a declared input above 60 MiB", async () => {
  const s = await setup(async (job) => {
    expect(
      (await readFile(path.join(job.directory, "input.pptx"))).length,
    ).toBe(31 * 1024 ** 2);
    const pdf = await PDFDocument.create();
    pdf.addPage([960, 540]);
    await writeFile(path.join(job.directory, "output.pdf"), await pdf.save());
    await writeFile(
      path.join(job.directory, "expected.json"),
      JSON.stringify({ visible: 1, width: 960, height: 540 }),
    );
  });
  const job = await (await s.api("/jobs", "POST")).json();
  expect(
    (await s.api(`/jobs/${job.id}/input`, "PUT", "x".repeat(31 * 1024 ** 2)))
      .status,
  ).toBe(202);
  await s.wait(job.id, "succeeded");
  const next = await (await s.api("/jobs", "POST")).json();
  const status = await new Promise<number>((resolve, reject) => {
    const req = request(
      `${s.url}/jobs/${next.id}/input`,
      {
        method: "PUT",
        headers: {
          origin,
          cookie: s.cookie,
          "Content-Type": mime,
          "Content-Length": 60 * 1024 ** 2 + 1,
        },
      },
      (res) => {
        res.resume();
        resolve(res.statusCode!);
      },
    );
    req.on("error", reject);
    req.end();
  });
  expect(status).toBe(413);
});

it("rejects Word options and the wrong upload format", async () => {
  const s = await setup();
  for (const options of [
    { revisionView: "final" },
    { omitComments: true },
    { useAvailableFonts: true },
    { extra: true },
  ])
    expect((await s.api("/jobs", "POST", JSON.stringify(options))).status).toBe(
      400,
    );
  const job = await (await s.api("/jobs", "POST")).json();
  expect(
    (
      await s.api(
        `/jobs/${job.id}/input`,
        "PUT",
        "x",
        s.cookie,
        "application/pdf",
      )
    ).status,
  ).toBe(415);
  expect(
    (await s.api(`/jobs/${job.id}`, "GET", undefined, "ppt_session=unsigned"))
      .status,
  ).toBe(401);
});

it("checks output scope before serving, deletes inputs before success, and deletes results", async () => {
  const s = await setup();
  const job = await (await s.api("/jobs", "POST")).json();
  expect(
    (await s.api(`/jobs/${job.id}/input`, "PUT", "synthetic-input")).status,
  ).toBe(202);
  expect((await s.wait(job.id, "succeeded")).pages).toBe(1);
  expect(await readdir(s.service.jobs.get(job.id)!.directory)).toEqual([
    "output.pdf",
  ]);
  expect((await s.api(`/jobs/${job.id}/result`)).status).toBe(200);
  await s.api(`/jobs/${job.id}`, "DELETE");
  expect((await s.api(`/jobs/${job.id}/result`)).status).not.toBe(200);
});

it("cancellation stays final when an executor returns late", async () => {
  let finish!: () => void;
  const gate = new Promise<void>((resolve) => {
    finish = resolve;
  });
  const s = await setup(async () => gate);
  const job = await (await s.api("/jobs", "POST")).json();
  await s.api(`/jobs/${job.id}/input`, "PUT", "synthetic-input");
  await s.api(`/jobs/${job.id}`, "DELETE");
  finish();
  await s.wait(job.id, "cancelled");
  expect((await s.api(`/jobs/${job.id}/result`)).status).not.toBe(200);
});

it("independently rejects mismatched pages, geometry, notes and active PDF actions", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "ppt-output-check-"));
  cleanup.push(() => rm(root, { recursive: true, force: true }));
  const policy = { ppt: true, visible: 1, width: 960, height: 540 };
  const file = path.join(root, "output.pdf");
  const pdf = await PDFDocument.create();
  const page = pdf.addPage([960, 540]);
  await writeFile(file, await pdf.save());
  await expect(checkPdf(file, policy)).resolves.toEqual({ pages: 1 });
  await expect(checkPdf(file, { ...policy, visible: 2 })).rejects.toThrow();
  await expect(checkPdf(file, { ...policy, width: 720 })).rejects.toThrow();
  const note = pdf.context.obj({
    Type: "Annot",
    Subtype: "Text",
    Contents: PDFString.of("SYNTHETIC_NOTES_SECRET"),
    Rect: [0, 0, 10, 10],
  });
  page.node.set(
    PDFName.of("Annots"),
    pdf.context.obj([pdf.context.register(note)]),
  );
  await writeFile(file, await pdf.save());
  await expect(checkPdf(file, policy)).rejects.toThrow();
  page.node.delete(PDFName.of("Annots"));
  pdf.catalog.set(
    PDFName.of("OpenAction"),
    pdf.context.obj({ S: "JavaScript", JS: PDFString.of("synthetic") }),
  );
  await writeFile(file, await pdf.save());
  await expect(checkPdf(file, policy)).rejects.toThrow();
});
