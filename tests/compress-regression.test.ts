import { expect, test } from "vitest";
import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import createQpdf from "@neslinesli93/qpdf-wasm";
import { PDFDocument } from "pdf-lib";
import { probePdf } from "../src/core/probe";
import {
  compressionArgs,
  summarizeCompression,
  type CompressionLevel,
} from "../src/compress/model";

const root = "tests/fixtures/m5/";
const ordinary = [
  "normal-a4",
  "mixed-page-size",
  "landscape",
  "100-pages",
  "scanned",
  "form",
  "chinese",
  "japanese",
  "image-heavy",
];

async function qpdf(bytes: Uint8Array, level: CompressionLevel) {
  const wasm = pathToFileURL(
    process.cwd() + "/node_modules/@neslinesli93/qpdf-wasm/dist/qpdf.wasm",
  ).href;
  const module = await createQpdf({
    locateFile: () => wasm,
    noInitialRun: true,
  } as Parameters<typeof createQpdf>[0]);
  const fs = module.FS as typeof module.FS & {
    writeFile: (path: string, data: Uint8Array) => void;
  };
  fs.writeFile("/input.pdf", bytes);
  module.callMain([...compressionArgs(level), "/input.pdf", "/output.pdf"]);
  return fs.readFile("/output.pdf").slice();
}

for (const name of ordinary)
  test(`M6 fixed regression compresses and reopens ${name}.pdf`, async () => {
    const source = new Uint8Array(await readFile(root + name + ".pdf"));
    const before = await PDFDocument.load(source);
    const candidate = await qpdf(
      source,
      name === "image-heavy" || name === "scanned" ? "recommended" : "quality",
    );
    const summary = summarizeCompression(
      source.byteLength,
      candidate.byteLength,
      "quality",
    );
    const output = summary.alreadyOptimized ? source : candidate;
    expect(output.byteLength).toBeLessThanOrEqual(source.byteLength);
    expect((await probePdf(output, "preview")).ok).toBe(true);
    const after = await PDFDocument.load(output);
    expect(after.getPageCount()).toBe(before.getPageCount());
    expect(after.getPages().map((page) => page.getSize())).toEqual(
      before.getPages().map((page) => page.getSize()),
    );
  }, 30000);

for (const name of ["encrypted", "corrupted", "large-50mb"])
  test(`M6 fixed regression refuses ${name}.pdf before compression`, async () => {
    const source = new Uint8Array(await readFile(root + name + ".pdf"));
    expect((await probePdf(source, "preview")).ok).toBe(false);
  });
