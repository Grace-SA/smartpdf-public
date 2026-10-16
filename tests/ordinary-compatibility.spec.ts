import { test, expect, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { PDFDocument, PDFArray, PDFName, PDFDict } from "pdf-lib";
import { inspectTags } from "../src/combine/tags";

async function selectFixtures(
  page: Page,
  paths: string[],
  browserName: string,
) {
  if (browserName !== "webkit") {
    await page.locator("#combine-files").setInputFiles(paths);
    return;
  }
  // Browser-owned synthetic files avoid platform file-picker dependencies.
  // Match the mobile harness; no app API
  // is bypassed and parsing/generation still run while networking is disabled.
  const files = await Promise.all(
    paths.map(async (path) => ({
      name: path.split("/").at(-1)!,
      bytes: [...(await readFile(path))],
    })),
  );
  await page.locator("#combine-files").evaluate((element, inputs) => {
    const transfer = new DataTransfer();
    for (const input of inputs)
      transfer.items.add(
        new File([new Uint8Array(input.bytes)], input.name, {
          type: "application/pdf",
        }),
      );
    (element as HTMLInputElement).files = transfer.files;
    element.dispatchEvent(new Event("change", { bubbles: true }));
  }, files);
}

test("ordinary scan, tagged link, comments and wrapped JPEG complete an offline saved task", async ({
  page,
  context,
  browserName,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await expect(page.locator("#combine-files")).toBeVisible();
  // Windows WebKit offline emulation also blocks local FileReader. Blocking
  // HTTP requests tests network independence, not real-device offline behavior.
  if (browserName === "webkit")
    await context.route(/^https?:/, (route) => route.abort());
  else await context.setOffline(true);
  await selectFixtures(
    page,
    ["scan", "tagged-link", "comments", "wrapped-image"].map(
      (n) => `tests/fixtures/combine/ordinary-${n}.pdf`,
    ),
    browserName,
  );
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 4", { exact: true })).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save PDF", exact: true }).click();
  const result = await download,
    file = await result.path();
  const bytes = await readFile(file!),
    doc = await PDFDocument.load(bytes);
  expect(inspectTags(doc)!.objectUses.size).toBe(1);
  expect(
    doc.getPage(2).node.lookup(PDFName.of("Annots"), PDFArray).size(),
  ).toBe(3);
  await page
    .getByRole("button", { name: "Undo Combine PDFs", exact: true })
    .click();
  await expect(page.locator(".canvas-host canvas")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Redo Combine PDFs", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 4", { exact: true })).toBeVisible();
});

test("custom roles and an empty layer catalog survive an offline save", async ({
  page,
  context,
  browserName,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await expect(page.locator("#combine-files")).toBeVisible();
  // Windows WebKit offline emulation also blocks local FileReader. Blocking
  // HTTP requests tests network independence, not real-device offline behavior.
  if (browserName === "webkit")
    await context.route(/^https?:/, (route) => route.abort());
  else await context.setOffline(true);
  await selectFixtures(
    page,
    [
      "tests/fixtures/combine/custom-role.pdf",
      "tests/fixtures/combine/empty-layers.pdf",
    ],
    browserName,
  );
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save PDF", exact: true }).click();
  const download = await pending;
  const out = await PDFDocument.load(await readFile((await download.path())!));
  expect(inspectTags(out)!.unmappedRoles.has("Strong")).toBe(true);
  await page.getByRole("button", { name: "Next →", exact: true }).click();
  await expect(page.getByText("Page 2 of 2", { exact: true })).toBeVisible();
});

test("indexed leaf tags and reconstructed bare layers survive an offline mixed save", async ({
  page,
  context,
  browserName,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await expect(page.locator("#combine-files")).toBeVisible();
  if (browserName === "webkit")
    await context.route(/^https?:/, (route) => route.abort());
  else await context.setOffline(true);
  await selectFixtures(
    page,
    [
      "tests/fixtures/combine/indexed-artifact.pdf",
      "tests/fixtures/combine/unconfigured-layer.pdf",
      "tests/fixtures/combine/layer-off.pdf",
    ],
    browserName,
  );
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 3", { exact: true })).toBeVisible();
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save PDF", exact: true }).click();
  const download = await pending;
  const bytes = await readFile((await download.path())!);
  const doc = await PDFDocument.load(bytes);
  expect(inspectTags(doc)!.detached).toHaveLength(1);
  const oc = doc.catalog.lookup(PDFName.of("OCProperties"), PDFDict);
  expect(oc.lookup(PDFName.of("OCGs"), PDFArray).size()).toBe(2);
  expect(
    oc
      .lookup(PDFName.of("D"), PDFDict)
      .lookup(PDFName.of("ON"), PDFArray)
      .size(),
  ).toBe(1);
  await page.getByRole("button", { name: "Next →", exact: true }).click();
  await expect(page.getByText("Page 2 of 3", { exact: true })).toBeVisible();
});
