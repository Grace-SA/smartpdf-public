import { test, expect } from "@playwright/test";
import { PDFDocument } from "pdf-lib";
import { deflateSync } from "node:zlib";
import { makeFixture } from "./fixtures";

test("compressed expansion and oversized inline images preserve the last valid preview", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page.locator("#pdf-file").setInputFiles({
    name: "valid.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(await makeFixture()),
  });
  await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
  for (const kind of ["expansion", "inline-image"]) {
    const doc = await PDFDocument.create();
    const p = doc.addPage();
    const stream =
      kind === "expansion"
        ? doc.context.stream(deflateSync(Buffer.alloc(9 * 1024 * 1024, 32)), {
            Filter: "FlateDecode",
          })
        : doc.context.stream("q BI /W 5000 /H 5000 /BPC 8 /CS /RGB ID x EI Q");
    p.node.addContentStream(doc.context.register(stream));
    await page.locator("#pdf-file").setInputFiles({
      name: `${kind}.pdf`,
      mimeType: "application/pdf",
      buffer: Buffer.from(await doc.save()),
    });
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "valid.pdf" }),
    ).toBeVisible();
    await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
    await expect(page.locator("#pdf-file")).toBeEnabled();
    await expect(page.locator("canvas")).toBeVisible();
  }
});
