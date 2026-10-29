import { describe, expect, it, vi } from "vitest";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import createQpdf from "@neslinesli93/qpdf-wasm";
import { getDocument } from "pdfjs-dist/legacy/build/pdf.mjs";
import { validPassword, protectionArgs } from "../src/protect/model";
import { generateProtected } from "../src/protect/generate";
import {
  inspectProtect,
  structureDigest,
  verifyEncryption,
} from "../src/protect/structure";
import { PDFDocument, PDFName, PDFString } from "pdf-lib";
import { makeFixture as fixture } from "./fixtures";

const wasm = pathToFileURL(
  process.cwd() + "/node_modules/@neslinesli93/qpdf-wasm/dist/qpdf.wasm",
).href;
const engine = () => createQpdf({ locateFile: () => wasm });
const source = () =>
  readFile("docs/ux/public-synthetic-only/demo-a.pdf").then(
    (b) => new Uint8Array(b),
  );

for (const name of [
  "normal-a4",
  "mixed-page-size",
  "landscape",
  "100-pages",
  "scanned",
  "form",
  "chinese",
  "japanese",
  "image-heavy",
  "200-pages",
  "unusual-page-sizes",
]) {
  it(`M11 frozen regression preserves ${name}`, async () => {
    const input = new Uint8Array(
      await readFile(`tests/fixtures/m5/${name}.pdf`),
    );
    const output = await generateProtected(
      input,
      "Synthetic-M11-Only!",
      await engine(),
    );
    expect(output.pages).toBe((await PDFDocument.load(input)).getPageCount());
    await mkdir(".research/m11/regression-outputs", { recursive: true });
    await writeFile(
      `.research/m11/regression-outputs/${name}.pdf`,
      output.bytes,
    );
  }, 30000);
}
for (const name of [
  "encrypted",
  "corrupted",
  "large-50mb",
  "100mb",
  "zero-pages",
]) {
  it(`M11 frozen refusal ${name}`, async () => {
    await expect(
      inspectProtect(
        new Uint8Array(await readFile(`tests/fixtures/m5/${name}.pdf`)),
      ),
    ).rejects.toThrow();
  });
}

describe("M11 password contract", () => {
  it("does not trim, normalize or truncate passwords", () => {
    for (const p of [
      "12345678",
      "--option-password",
      "  pass phrase  ",
      "中文密码测试-123",
      "emoji-😀-123",
      "sample-e\u0301-123",
      "x".repeat(127),
    ]) {
      expect(validPassword(p)).toBe(true);
      expect(protectionArgs(p)).toContain(`--user-password=${p}`);
    }
    for (const p of [
      "",
      "short",
      "        ",
      "x".repeat(128),
      "中".repeat(43),
      "password\0",
      "password\n",
      "password\ud800",
      "pass\u200bword",
    ])
      expect(validPassword(p)).toBe(false);
    expect(validPassword("password1", "password2")).toBe(false);
  });
});

for (const [id, password] of [
  ["ascii", "Synthetic-M11-Only!"],
  ["unicode", "中文密码测试-123"],
  ["spaces", "  pass phrase  "],
  ["option", "--option-password"],
  ["emoji", "emoji-😀-123"],
  ["combining", "sample-e\u0301-123"],
  ["max", "x".repeat(127)],
]) {
  it(`M11 independent PDF.js password checks: ${id}`, async () => {
    const input = await source();
    const original = input.slice();
    const output = await generateProtected(input, password!, await engine());
    expect(input).toEqual(original);
    expect(output.pages).toBe(6);
    for (const p of ["", "wrong-password", password!]) {
      const task = getDocument({
        data: output.bytes.slice(),
        password: p,
        verbosity: 0,
      });
      try {
        if (p === password) expect((await task.promise).numPages).toBe(6);
        else
          await expect(task.promise).rejects.toMatchObject({
            name: "PasswordException",
          });
      } finally {
        await task.destroy();
      }
    }
    await mkdir(".research/m11/outputs", { recursive: true });
    await writeFile(`.research/m11/outputs/${id}.pdf`, output.bytes);
  }, 30000);
}

it("M11 encryptions are not deterministic and temporary files are removed", async () => {
  const e = await engine();
  const a = await generateProtected(await source(), "Synthetic-M11-Only!", e);
  expect(() => e.FS.readFile("/input.pdf")).toThrow();
  expect(() => e.FS.readFile("/protected.pdf")).toThrow();
  expect(() => e.FS.readFile("/verified.pdf")).toThrow();
  const b = await generateProtected(
    await source(),
    "Synthetic-M11-Only!",
    await engine(),
  );
  expect(a.bytes).not.toEqual(b.bytes);
});

it("M11 structural fingerprint detects text and metadata changes", async () => {
  const a = await source();
  const d = await PDFDocument.load(a, { updateMetadata: false });
  d.setTitle("Changed synthetic title");
  expect(await structureDigest(await d.save())).not.toBe(
    await structureDigest(a),
  );
});

for (const kind of [
  "signature",
  "pdfa",
  "pdfx",
  "javascript",
  "attachment",
  "zero-pages",
  "huge-page",
  "too-many-pages",
  "encrypted-marker",
] as const)
  it(`M11 refuses ${kind} without encryption`, async () => {
    await expect(inspectProtect(await fixture(kind))).rejects.toThrow();
  });

it("M11 refuses C2PA metadata and zero bytes", async () => {
  const doc = await PDFDocument.load(await source());
  doc.catalog.set(
    PDFName.of("Metadata"),
    doc.context.register(
      doc.context.stream(
        new TextEncoder().encode(
          '<x:xmpmeta xmlns:x="adobe:ns:meta/"><c2pa>synthetic</c2pa></x:xmpmeta>',
        ),
        { Type: "Metadata", Subtype: "XML" },
      ),
    ),
  );
  await expect(inspectProtect(await doc.save())).rejects.toThrow();
  await expect(inspectProtect(new Uint8Array())).rejects.toThrow();
});

it("M11 keeps ordinary logical strings across serialization", async () => {
  const doc = await PDFDocument.load(await source());
  doc.catalog.set(
    PDFName.of("SyntheticCustom"),
    PDFString.of("plain synthetic metadata"),
  );
  await expect(
    generateProtected(await doc.save(), "Synthetic-M11-Only!", await engine()),
  ).resolves.toHaveProperty("pages", 6);
});

for (const name of ["navigation-a", "layer-on", "final-tags"]) {
  it(`M11 preserves rich structure ${name}`, async () => {
    const bytes = new Uint8Array(
      await readFile(`tests/fixtures/combine/${name}.pdf`),
    );
    const output = await generateProtected(
      bytes,
      "Synthetic-M11-Only!",
      await engine(),
    );
    await mkdir(".research/m11/rich-outputs", { recursive: true });
    await writeFile(`.research/m11/rich-outputs/${name}.pdf`, output.bytes);
  });
}
it("M11 refuses plaintext masquerading as protected output", async () => {
  await expect(verifyEncryption(await source())).rejects.toMatchObject({
    code: "VERIFY",
  });
});
it("M11 refuses changed decrypted contents and cleans all temporary files", async () => {
  const e = await engine(),
    native = e.callMain.bind(e);
  e.callMain = (args) => {
    const result = native(args);
    if (args.includes("--decrypt"))
      (
        e.FS as typeof e.FS & {
          writeFile: (path: string, bytes: Uint8Array) => void;
        }
      ).writeFile("/verified.pdf", new Uint8Array([37, 80, 68, 70]));
    return result;
  };
  await expect(
    generateProtected(await source(), "Synthetic-M11-Only!", e),
  ).rejects.toThrow();
  for (const p of ["/input.pdf", "/protected.pdf", "/verified.pdf"])
    expect(() => e.FS.readFile(p)).toThrow();
});
it("M11 refuses to encrypt when the secure random source fails", async () => {
  const e = await engine(),
    input = await source();
  const random = vi.spyOn(crypto, "getRandomValues").mockImplementation(() => {
    throw Error("synthetic entropy failure");
  });
  try {
    await expect(
      generateProtected(input, "Synthetic-M11-Only!", e),
    ).rejects.toThrow();
    for (const p of ["/input.pdf", "/protected.pdf", "/verified.pdf"])
      expect(() => e.FS.readFile(p)).toThrow();
  } finally {
    random.mockRestore();
  }
});
