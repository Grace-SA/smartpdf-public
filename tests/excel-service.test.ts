import { afterEach, expect, it } from "vitest";
import { mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import type { AddressInfo } from "node:net";
import { PDFDocument } from "pdf-lib";
import { createWordService, type Task } from "../server/word/service.mjs";

const origin = "http://127.0.0.1:4240";
const settings = {
  sheets: [0],
  orientation: "keep",
  paper: "keep",
  scale: "width",
};
const cleanup: (() => Promise<void>)[] = [];
afterEach(async () => {
  await Promise.all(cleanup.splice(0).map((fn) => fn()));
});
async function setup(
  execute?: (job: Task) => Promise<void>,
  enableExcel = true,
) {
  const root = await mkdtemp(path.join(tmpdir(), "excel-service-"));
  const service = await createWordService({
    root,
    origin,
    enableExcel,
    execute:
      execute ||
      (async (job) => {
        expect(job.kind).toBe("excel");
        expect(
          JSON.parse(
            await readFile(path.join(job.directory, "options.json"), "utf8"),
          ),
        ).toEqual(settings);
        expect(
          await readFile(path.join(job.directory, "input.xlsx"), "utf8"),
        ).toBe("synthetic transport input");
        const pdf = await PDFDocument.create();
        pdf.addPage();
        await writeFile(
          path.join(job.directory, "output.pdf"),
          await pdf.save(),
        );
        await writeFile(
          path.join(job.directory, "prepared.xlsx"),
          "synthetic prepared input",
        );
      }),
  });
  await new Promise<void>((resolve) =>
    service.server.listen(0, "127.0.0.1", resolve),
  );
  const base = `http://127.0.0.1:${(service.server.address() as AddressInfo).port}`;
  cleanup.push(async () => {
    await service.close();
    await rm(root, { recursive: true, force: true });
  });
  const session = await fetch(base + "/api/excel/session");
  if (enableExcel)
    expect(session.headers.get("set-cookie")).toContain("Path=/api/excel;");
  const cookie = session.headers.get("set-cookie")?.split(";")[0] || "";
  const api = (
    suffix: string,
    method = "GET",
    body?: string,
    options: unknown = settings,
    owner = cookie,
  ) =>
    fetch(base + "/api/excel" + suffix, {
      method,
      headers: {
        Cookie: owner,
        Origin: origin,
        ...(body === undefined
          ? {}
          : {
              "Content-Type":
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              "X-Excel-Options": JSON.stringify(options),
            }),
      },
      body,
    });
  const create = async () =>
    (await (await api("/jobs", "POST")).json()).id as string;
  const wait = async (id: string, state: string) => {
    for (let n = 0; n < 100; n++) {
      const job = await (await api(`/jobs/${id}`)).json();
      if (job.state === state) return job;
      await new Promise((resolve) => setTimeout(resolve, 20));
    }
    throw new Error("State not reached");
  };
  return { root, base, api, create, wait, service, cookie };
}
it("validates a PDF, removes both original and prepared workbook, and confirms deletion", async () => {
  const t = await setup();
  const id = await t.create();
  expect(
    (await t.api(`/jobs/${id}/input`, "PUT", "synthetic transport input"))
      .status,
  ).toBe(202);
  await t.wait(id, "succeeded");
  expect(await readdir(path.join(t.root, id))).toEqual([
    "options.json",
    "output.pdf",
  ]);
  expect((await t.api(`/jobs/${id}/result`)).headers.get("content-type")).toBe(
    "application/pdf",
  );
  expect((await t.api(`/jobs/${id}/input`, "PUT", "duplicate")).status).toBe(
    409,
  );
  await t.api(`/jobs/${id}`, "DELETE");
  expect((await t.api(`/jobs/${id}/result`)).status).toBe(409);
  expect(await readdir(t.root)).toEqual([]);
});
it("keeps Word and Excel cookies scoped separately and denies cross-tool task IDs", async () => {
  const t = await setup();
  const id = await t.create();
  const response = await fetch(t.base + "/api/word/session");
  expect(response.headers.get("set-cookie")).toContain("Path=/api/word;");
  const wordCookie = response.headers.get("set-cookie")!.split(";")[0]!;
  expect(
    (
      await fetch(t.base + `/api/word/jobs/${id}`, {
        headers: { Cookie: t.cookie },
      })
    ).status,
  ).toBe(401);
  expect(
    (await t.api(`/jobs/${id}`, "GET", undefined, settings, wordCookie)).status,
  ).toBe(401);
  expect(
    (
      await t.api(
        `/jobs/${id}`,
        "GET",
        undefined,
        settings,
        "excel_session=forged",
      )
    ).status,
  ).toBe(401);
  expect(
    (
      await fetch(t.base + "/api/excel/jobs", {
        method: "POST",
        headers: { Cookie: t.cookie, Origin: "https://example.invalid" },
      })
    ).status,
  ).toBe(403);
});
it.each([
  { ...settings, sheets: [] },
  { ...settings, sheets: [0, 0] },
  { ...settings, sheets: [true] },
  { ...settings, scale: "singlePageSheets" },
  { ...settings, url: "https://example.invalid" },
])("refuses invalid settings without creating an input", async (value) => {
  const t = await setup();
  const id = await t.create();
  expect((await t.api(`/jobs/${id}/input`, "PUT", "input", value)).status).toBe(
    400,
  );
  expect(await readdir(path.join(t.root, id))).toEqual([]);
});
it("keeps a cancelled running conversion final and removes late output", async () => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const t = await setup(async (job) => {
    await gate;
    const pdf = await PDFDocument.create();
    pdf.addPage();
    await writeFile(path.join(job.directory, "output.pdf"), await pdf.save());
  });
  const id = await t.create();
  await t.api(`/jobs/${id}/input`, "PUT", "synthetic transport input");
  const cancelled = await (await t.api(`/jobs/${id}`, "DELETE")).json();
  expect(cancelled.state).toBe("cancelled");
  release();
  for (let i = 0; i < 100 && (await readdir(t.root)).length; i++)
    await new Promise((resolve) => setTimeout(resolve, 20));
  expect((await (await t.api(`/jobs/${id}`)).json()).state).toBe("cancelled");
  expect(await readdir(t.root)).toEqual([]);
});

it("keeps Excel API disabled unless explicitly enabled", async () => {
  const t = await setup(undefined, false);
  const response = await fetch(t.base + "/api/excel/session");
  expect(response.status).toBe(404);
  expect(response.headers.get("set-cookie")).toBeNull();
  expect((await fetch(t.base + "/api/word/session")).status).toBe(200);
});
