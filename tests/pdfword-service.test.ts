import { afterEach, expect, it } from "vitest";
import { mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import type { AddressInfo } from "node:net";
import type { Task } from "../server/word/service.mjs";
import { createPdfWordService } from "../server/pdfword/service.mjs";
import { checkDocx } from "../server/pdfword/docx-check.mjs";

const outputMime =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const bytes = execFileSync(
  process.env.PYTHON || (process.platform === "win32" ? "python" : "python3"),
  [
    "-B",
    "-c",
    `
import io,sys
from docx import Document
d=Document()
for k,r in list(d.part.package.rels.items()):
 if r.reltype.endswith('/thumbnail'): del d.part.package.rels[k]
d.add_paragraph('Synthetic editable text 123.45')
b=io.BytesIO();d.save(b);sys.stdout.buffer.write(b.getvalue())
`,
  ],
  { env: { ...process.env, PYTHONPATH: path.resolve(".local-python") } },
);
const cleanup: (() => Promise<void>)[] = [];
afterEach(async () => {
  for (const fn of cleanup.splice(0)) await fn();
});
async function setup(execute?: (job: Task) => Promise<void>) {
  const root = await mkdtemp(path.join(tmpdir(), "pdfword-synthetic-"));
  const origin = "http://127.0.0.1:4240";
  const service = await createPdfWordService({
    root,
    origin,
    execute:
      execute ||
      (async (job: Task) => {
        expect(
          await readFile(path.join(job.directory, "input.pdf"), "utf8"),
        ).toBe("synthetic");
        await writeFile(path.join(job.directory, "output.docx"), bytes);
        await writeFile(
          path.join(job.directory, "expected.json"),
          '{"pages":2}',
        );
      }),
  });
  await new Promise<void>((r) => service.server.listen(0, "127.0.0.1", r));
  cleanup.push(async () => {
    await service.close();
    await rm(root, { recursive: true, force: true });
  });
  const url = `http://127.0.0.1:${(service.server.address() as AddressInfo).port}/api/pdfword`;
  const session = await fetch(url + "/session");
  const cookie = session.headers.get("set-cookie")!.split(";")[0]!;
  const api = (
    suffix: string,
    method = "GET",
    body?: string,
    owner = cookie,
    mime = "application/pdf",
  ) =>
    fetch(url + suffix, {
      method,
      body,
      headers: { origin, cookie: owner, "Content-Type": mime },
    });
  async function wait(id: string, state: string) {
    for (let i = 0; i < 150; i++) {
      const next = await (await api(`/jobs/${id}`)).json();
      if (next.state === state && !next.cleanupPending) return next;
      await new Promise((r) => setTimeout(r, 20));
    }
    throw Error("Task did not reach expected state");
  }
  return { service, root, url, api, cookie, wait };
}

it("separates owners, enforces PDF uploads, options and origin", async () => {
  const s = await setup();
  expect(s.cookie).toMatch(/^pdfword_session=/);
  expect((await (await s.api("/session")).json()).maxBytes).toBe(
    30 * 1024 ** 2,
  );
  expect(
    (
      await fetch(s.url + "/jobs", {
        method: "POST",
        headers: { cookie: s.cookie },
      })
    ).status,
  ).toBe(403);
  expect(
    (await fetch(s.url.replace("/pdfword", "/word") + "/session")).status,
  ).toBe(404);
  expect(
    (await s.api("/jobs", "POST", undefined, "word_session=unsigned")).status,
  ).toBe(401);
  expect(
    (await s.api("/jobs", "POST", '{"revisionView":"final"}')).status,
  ).toBe(400);
  const job = await (await s.api("/jobs", "POST")).json();
  expect(
    (
      await s.api(
        `/jobs/${job.id}/input`,
        "PUT",
        "synthetic",
        s.cookie,
        outputMime,
      )
    ).status,
  ).toBe(415);
});

it("validates Word independently, removes the source and metadata before download, then deletes the result", async () => {
  const s = await setup();
  const job = await (await s.api("/jobs", "POST")).json();
  expect(
    (await s.api(`/jobs/${job.id}/input`, "PUT", "synthetic")).status,
  ).toBe(202);
  expect((await s.wait(job.id, "succeeded")).pages).toBe(2);
  expect(await readdir(s.service.jobs.get(job.id)!.directory)).toEqual([
    "output.docx",
  ]);
  const result = await s.api(`/jobs/${job.id}/result`);
  expect(result.headers.get("content-type")).toBe(outputMime);
  expect(result.headers.get("content-disposition")).toContain("converted.docx");
  expect(Buffer.from(await result.arrayBuffer()).equals(bytes)).toBe(true);
  await s.api(`/jobs/${job.id}`, "DELETE");
  expect((await s.api(`/jobs/${job.id}/result`)).status).not.toBe(200);
});

it("keeps cancellation final when conversion returns late", async () => {
  let finish!: () => void;
  const gate = new Promise<void>((r) => {
    finish = r;
  });
  const s = await setup(async () => gate);
  const job = await (await s.api("/jobs", "POST")).json();
  await s.api(`/jobs/${job.id}/input`, "PUT", "synthetic");
  await s.api(`/jobs/${job.id}`, "DELETE");
  finish();
  await s.wait(job.id, "cancelled");
  expect((await s.api(`/jobs/${job.id}/result`)).status).not.toBe(200);
});

it("refuses corrupt Word output and does not retain a partial download", async () => {
  const s = await setup(async (job) => {
    await writeFile(path.join(job.directory, "output.docx"), "PKbroken");
    await writeFile(path.join(job.directory, "expected.json"), '{"pages":1}');
  });
  const job = await (await s.api("/jobs", "POST")).json();
  await s.api(`/jobs/${job.id}/input`, "PUT", "synthetic");
  await s.wait(job.id, "failed");
  expect((await s.api(`/jobs/${job.id}/result`)).status).not.toBe(200);
  const file = path.join(s.root, "check.docx");
  await writeFile(file, bytes);
  await expect(checkDocx(file)).resolves.toBeTruthy();
  const damaged = Buffer.from(bytes);
  damaged[100] = damaged[100]! ^ 1;
  await writeFile(file, damaged);
  await expect(checkDocx(file)).rejects.toThrow();
});

it("refuses external relationships, macros, entities, duplicate parts and escaping ZIP names", async () => {
  const s = await setup();
  const file = path.join(s.root, "unsafe.docx");
  for (const kind of [
    "external",
    "external-escaped",
    "external-prefixed",
    "external-implicit",
    "macro",
    "entity",
    "duplicate",
    "escape",
  ]) {
    const altered = execFileSync(
      process.env.PYTHON ||
        (process.platform === "win32" ? "python" : "python3"),
      [
        "-B",
        "-c",
        `
import io,sys,zipfile,warnings
warnings.simplefilter('ignore')
kind=sys.argv[1]; output=io.BytesIO()
with zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read())) as source, zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as target:
 for name in source.namelist():
  data=source.read(name)
  if kind=='macro' and name=='[Content_Types].xml': data=data.replace(b'wordprocessingml.document.main+xml',b'wordprocessingml.document.macroEnabled.main+xml')
  if kind=='entity' and name=='word/document.xml': data=b'<!DOCTYPE x [<!ENTITY a "bad">]>'+data
  if kind=='external' and name=='_rels/.rels': data=data.replace(b'</Relationships>',b'<Relationship Id="unsafe" Type="https://example.invalid" Target="https://example.invalid" TargetMode="External"/></Relationships>')
  if kind=='external-escaped' and name=='_rels/.rels': data=data.replace(b'</Relationships>',b'<Relationship Id="unsafe" Type="https://example.invalid" Target="https://example.invalid" TargetMode="Extern&#97;l"/></Relationships>')
  if kind=='external-prefixed' and name=='_rels/.rels': data=data.replace(b'</Relationships>',b'<r:Relationship xmlns:r="http://schemas.openxmlformats.org/package/2006/relationships" Id="unsafe" Type="https://example.invalid" Target="https://example.invalid" TargetMode="Extern&#x61;l"/></Relationships>')
  if kind=='external-implicit' and name=='_rels/.rels': data=data.replace(b'</Relationships>',b'<Relationship Id="unsafe" Type="https://example.invalid" Target="https://example.invalid"/></Relationships>')
  target.writestr(name,data)
 if kind=='duplicate': target.writestr('word/document.xml',source.read('word/document.xml'))
 if kind=='escape': target.writestr('../unsafe.xml',b'<x/>')
sys.stdout.buffer.write(output.getvalue())
`,
        kind,
      ],
      { input: bytes },
    );
    await writeFile(file, altered);
    await expect(checkDocx(file)).rejects.toThrow();
  }
});
