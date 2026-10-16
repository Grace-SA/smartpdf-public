import { test, expect } from "vitest";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { PDFDocument } from "pdf-lib";
import { inspectSign, signPdf } from "../src/sign/generate";
import { inspectPdf, combinePdfs } from "../src/combine/generate";
import { organizePdf } from "../src/organize/generate";
import { splitPdf } from "../src/split/generate";
import { generatePhotos } from "../src/photos/generate";
import { defaultSettings } from "../src/photos/model";
import { probePdf } from "../src/core/probe";
const root = "tests/fixtures/m5/";
const names = [
  "normal-a4",
  "mixed-page-size",
  "landscape",
  "100-pages",
  "scanned",
  "form",
  "chinese",
  "japanese",
  "image-heavy",
  "encrypted",
  "corrupted",
  "large-50mb",
  "zero-pages",
  "200-pages",
  "100mb",
  "unusual-page-sizes",
];
for (const name of names)
  test(`fixed regression: ${name}.pdf`, async () => {
    const bytes = new Uint8Array(await readFile(root + name + ".pdf"));
    if (
      ["encrypted", "corrupted", "large-50mb", "zero-pages", "100mb"].includes(
        name,
      )
    ) {
      expect((await probePdf(bytes, "preview")).ok).toBe(false);
      expect((await inspectPdf(bytes)).ok).toBe(false);
      await expect(inspectSign(bytes)).rejects.toThrow();
      await expect(combinePdfs([bytes, bytes], () => {})).rejects.toThrow();
      await expect(
        organizePdf(bytes, [{ id: "p", source: 0, turns: 0 }]),
      ).rejects.toThrow();
      await expect(
        splitPdf(bytes, [[0]], false, 60 * 1024 * 1024, () => {}),
      ).rejects.toThrow();
      return;
    }
    expect((await probePdf(bytes, "preview")).ok).toBe(true);
    const check = await inspectPdf(bytes);
    // This fixed passive form is supported; a future refusal is a regression.
    expect(check.ok).toBe(true);
    const { geometry } = await inspectSign(bytes),
      n = geometry.length;
    const image = new Uint8Array(await readFile(root + "signature.png"));
    const signed = await signPdf(
      bytes,
      [{ id: "a", bytes: image }],
      [
        {
          id: "s",
          asset: "a",
          page: n - 1,
          x: 20,
          y: 30,
          width: 120,
          height: 40,
        },
      ],
    );
    expect((await PDFDocument.load(signed)).getPageCount()).toBe(n);
    const plan = geometry.map((_, source) => ({
      id: String(source),
      source,
      turns: 0,
    }));
    expect(
      (
        await PDFDocument.load(await organizePdf(bytes, plan.reverse()))
      ).getPageCount(),
    ).toBe(n);
    const groups =
      n > 1 ? [[0], Array.from({ length: n - 1 }, (_, i) => i + 1)] : [[0]];
    if (name === "form")
      await expect(
        splitPdf(bytes, groups, false, 60 * 1024 * 1024, () => {}),
      ).rejects.toThrow();
    const split = await splitPdf(
      bytes,
      groups,
      name === "form",
      60 * 1024 * 1024,
      () => {},
    );
    expect(split.length).toBe(groups.length);
    const other = await PDFDocument.create();
    other.addPage();
    const more = await other.save();
    if (n < 200)
      expect(
        (
          await PDFDocument.load(await combinePdfs([bytes, more], () => {}))
        ).getPageCount(),
      ).toBe(n + 1);
    else
      await expect(combinePdfs([bytes, more], () => {})).rejects.toThrow(
        "200 pages",
      );
    await mkdir("docs/evidence/m5-output", { recursive: true });
    await writeFile(`docs/evidence/m5-output/${name}-signed.pdf`, signed);
  }, 60000);
test("M1 image generation stays compatible with M5 and existing transformations", async () => {
  const image = new Uint8Array(await readFile(root + "signature.png"));
  const bytes = await generatePhotos(
    [{ bytes: image, turns: 0 }],
    defaultSettings,
    () => {},
  );
  expect((await inspectSign(bytes)).geometry).toHaveLength(1);
});
