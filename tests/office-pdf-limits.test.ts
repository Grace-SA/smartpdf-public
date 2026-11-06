import { afterEach, expect, it } from "vitest";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { PDFDocument } from "pdf-lib";
import { checkPdf } from "../server/word/service.mjs";
import { probePdf } from "../src/core/probe";
import { makeFixture } from "./fixtures";

const roots: string[] = [];
it("keeps actions, geometry and complexity refusals in the Excel output preview scope", async () => {
  for (const [kind, reason] of [
    ["javascript", "actions"],
    ["launch", "actions"],
    ["deep", "complexity"],
    ["huge-page", "geometry"],
  ] as const) {
    expect(
      await probePdf(
        await makeFixture(kind),
        "preview",
        undefined,
        "excel-output",
      ),
    ).toMatchObject({ ok: false, reason });
  }
});
afterEach(async () => {
  await Promise.all(
    roots.splice(0).map((root) => rm(root, { recursive: true, force: true })),
  );
});
async function fixture(pages: number, text = false) {
  const root = await mkdtemp(path.join(tmpdir(), "office-budget-"));
  roots.push(root);
  const doc = await PDFDocument.create();
  for (let i = 0; i < pages; i++) {
    const page = doc.addPage();
    if (text)
      page.drawText(
        Array.from(
          { length: 40 },
          (_, row) =>
            `Synthetic page ${i + 1}, row ${row + 1}: bounded PDF validation`,
        ).join("\n"),
        { x: 30, y: 800, size: 10, lineHeight: 15 },
      );
  }
  const file = path.join(root, "synthetic.pdf");
  await writeFile(file, await doc.save());
  return file;
}
for (const pages of [200, 201, 500, 501]) {
  it(`keeps independent Word 200 / Excel 500 page boundaries at ${pages} pages`, async () => {
    const file = await fixture(pages);
    const bytes = new Uint8Array(await readFile(file));
    expect(
      await probePdf(bytes, "preview", undefined, "excel-output"),
    ).toMatchObject(
      pages <= 500 ? { ok: true, pages } : { ok: false, reason: "pages" },
    );
    if (pages === 201) {
      expect(await probePdf(bytes, "preview")).toMatchObject({
        ok: false,
        reason: "pages",
      });
      expect(
        await probePdf(bytes, "strict", undefined, "excel-output"),
      ).toMatchObject({ ok: false, reason: "pages" });
    }
    for (const kind of ["word", "excel"] as const) {
      if (pages <= (kind === "excel" ? 500 : 200))
        await expect(checkPdf(file, kind)).resolves.toEqual({ pages });
      else await expect(checkPdf(file, kind)).rejects.toThrow();
    }
    if (pages === 201) await expect(checkPdf(file)).rejects.toThrow();
  }, 30_000);
}
it("repeatedly validates a content-bearing 500-page Excel PDF within the unchanged worker budget", async () => {
  const file = await fixture(500, true);
  for (let attempt = 0; attempt < 3; attempt++)
    await expect(checkPdf(file, "excel")).resolves.toEqual({ pages: 500 });
}, 45_000);
