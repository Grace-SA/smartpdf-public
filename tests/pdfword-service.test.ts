import { afterEach, expect, it, vi } from "vitest";
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
  vi.unstubAllEnvs();
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

it("advertises the native adapter only for an opted-in configured reconstruction service", async () => {
  vi.stubEnv("PDFWORD_LOCAL_V2", "1");
  vi.stubEnv("PDFWORD_NATIVE_ENGINE", "stirling");
  vi.stubEnv("PDFWORD_STIRLING_RUNTIME", "");
  const missing = await setup();
  expect(
    (await (await missing.api("/session")).json()).capabilities.stirlingNative,
  ).toBe(false);
  vi.stubEnv("PDFWORD_STIRLING_RUNTIME", "/synthetic/runtime");
  const enabled = await setup();
  expect(
    (await (await enabled.api("/session")).json()).capabilities.stirlingNative,
  ).toBe(true);
  vi.stubEnv("PDFWORD_LOCAL_V2", "0");
  const baseline = await setup();
  expect(
    (await (await baseline.api("/session")).json()).capabilities.stirlingNative,
  ).toBe(false);
});

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
    "macro",
    "entity",
    "duplicate",
    "escape",
    "dangling",
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
  if kind=='dangling' and name=='_rels/.rels': data=data.replace(b'word/document.xml',b'word/missing.xml')
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

it("rejects a v2 manifest claiming unverified source pages, tables or images", async () => {
  const s = await setup(async (job) => {
    await writeFile(path.join(job.directory, "output.docx"), bytes);
    await writeFile(
      path.join(job.directory, "expected.json"),
      JSON.stringify({ schema: 2, pages: 2, images: 1, tables: 1 }),
    );
  });
  const job = await (await s.api("/jobs", "POST")).json();
  await s.api(`/jobs/${job.id}/input`, "PUT", "synthetic");
  const result = await s.wait(job.id, "failed");
  expect(result.failureCode).toBe("OUTPUT_INVALID");
  expect((await s.api(`/jobs/${job.id}/result`)).status).not.toBe(200);
});

it("independently checks page bookmarks, editable tables and embedded PNGs", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "pdfword-opc-"));
  cleanup.push(() => rm(root, { recursive: true, force: true }));
  const file = path.join(root, "image.docx");
  execFileSync(process.env.PYTHON || "python3", [
    "-B",
    "-c",
    `
import sys,io
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image
d=Document()
for k,r in list(d.part.package.rels.items()):
 if r.reltype.endswith('/thumbnail'):del d.part.package.rels[k]
p=d.add_paragraph('Editable text')
m=OxmlElement('w:bookmarkStart');m.set(qn('w:id'),'0');m.set(qn('w:name'),'smartpdf_page_1');p._p.append(m)
d.add_table(rows=2,cols=2).cell(0,0).text='123.45'
b=io.BytesIO();Image.new('RGB',(20,20),'red').save(b,format='PNG');b.seek(0);d.add_picture(b)
d.save(sys.argv[1])
`,
    file,
  ]);
  await expect(checkDocx(file)).resolves.toMatchObject({
    pages: 1,
    sourceMarkers: 1,
    tables: 1,
    images: 1,
  });
});

it("accepts an editable Office Math document without ordinary text runs", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "pdfword-math-"));
  cleanup.push(() => rm(root, { recursive: true, force: true }));
  const file = path.join(root, "math.docx");
  execFileSync(process.env.PYTHON || "python3", [
    "-B",
    "-c",
    `
import sys
from docx import Document
from docx.oxml import OxmlElement
d=Document()
for k,r in list(d.part.package.rels.items()):
 if r.reltype.endswith('/thumbnail'):del d.part.package.rels[k]
p=d.add_paragraph();m=OxmlElement('m:oMath');r=OxmlElement('m:r');t=OxmlElement('m:t');t.text='x=2';r.append(t);m.append(r);p._p.append(m)
d.save(sys.argv[1])
`,
    file,
  ]);
  await expect(checkDocx(file)).resolves.toMatchObject({
    tables: 0,
    images: 0,
  });
});

it.each([
  [true, true, true, true],
  [false, true, true, false],
  [true, false, true, false],
  [true, true, false, false],
])(
  "checks illustrated body with referenced margin text (%s, %s, %s)",
  async (image, text, referenced, valid) => {
    const root = await mkdtemp(path.join(tmpdir(), "pdfword-margin-"));
    cleanup.push(() => rm(root, { recursive: true, force: true }));
    const file = path.join(root, "margin.docx");
    execFileSync(process.env.PYTHON || "python3", [
      "-B",
      "-c",
      `
import sys,io
from docx import Document
from docx.oxml.ns import qn
from PIL import Image
d=Document()
for k,r in list(d.part.package.rels.items()):
 if r.reltype.endswith('/thumbnail'):del d.part.package.rels[k]
h=d.sections[0].header
h.paragraphs[0].text='Illustration title' if sys.argv[3]=='true' else ''
if sys.argv[2]=='true':
 b=io.BytesIO();Image.new('RGB',(20,20),'red').save(b,format='PNG');b.seek(0);d.add_picture(b)
if sys.argv[4]!='true':
 for element in list(d.sections[0]._sectPr):
  if element.tag==qn('w:headerReference'):element.getparent().remove(element)
d.save(sys.argv[1])
`,
      file,
      String(image),
      String(text),
      String(referenced),
    ]);
    if (valid)
      await expect(checkDocx(file)).resolves.toMatchObject({ images: 1 });
    else await expect(checkDocx(file)).rejects.toThrow();
  },
);
