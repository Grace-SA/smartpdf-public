import { test, expect } from "vitest";
import { readFile } from "node:fs/promises";
import { PDFDocument, PDFName } from "pdf-lib";
import { probePdf } from "../src/core/probe";

test("ordinary ICC output intent is not presented as a standard claim", async () => {
  const bytes = new Uint8Array(
    await readFile("tests/fixtures/combine/final-color.pdf"),
  );
  const preview = await probePdf(bytes, "preview");
  expect(preview.ok).toBe(true);
  if (preview.ok)
    expect(preview.previewFeatures ?? []).not.toContain("standard");
  expect((await probePdf(bytes, "combine")).ok).toBe(true);
});
test("actual standard declarations still require the ordinary-copy path", async () => {
  const bytes = new Uint8Array(
    await readFile("tests/fixtures/split/ordinary.pdf"),
  );
  const preview = await probePdf(bytes, "preview");
  expect(preview.ok).toBe(true);
  if (preview.ok) expect(preview.previewFeatures).toContain("standard");
  const edit = await probePdf(bytes, "combine");
  expect(edit.ok).toBe(false);
  if (!edit.ok) expect(edit.reasons).toContain("standard");
});
test("unvalidated output intent remains a preview warning and is not editable", async () => {
  const d = await PDFDocument.load(
    await readFile("tests/fixtures/combine/final-color.pdf"),
    { updateMetadata: false },
  );
  d.catalog.set(PDFName.of("OutputIntents"), d.context.obj([]));
  const bytes = await d.save({ updateFieldAppearances: false });
  const preview = await probePdf(bytes, "preview");
  expect(preview.ok).toBe(true);
  if (preview.ok) expect(preview.previewFeatures).toContain("standard");
  expect((await probePdf(bytes, "combine")).ok).toBe(false);
});
