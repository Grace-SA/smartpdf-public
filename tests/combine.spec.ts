import { test, expect, type Page } from "@playwright/test";
import { readFile, mkdir } from "node:fs/promises";
import { PDFDocument } from "pdf-lib";
import { inspectNavigation } from "../src/combine/navigation";
import { inspectLayers } from "../src/combine/layers";
import { inspectTags } from "../src/combine/tags";
async function open(page: Page) {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
}
async function add(page: Page, names: string[]) {
  await page
    .locator("#combine-files")
    .setInputFiles(names.map((n) => `tests/fixtures/${n}.pdf`));
  await expect(
    page.getByRole("button", { name: "Cancel combine task" }),
  ).toHaveCount(0);
}

test("layers and tags merge offline and survive saved output", async ({
  page,
  context,
}) => {
  await open(page);
  await context.setOffline(true);
  await add(page, [
    "combine/layer-off",
    "combine/tag-a",
    "combine/layer-on",
    "combine/tag-b",
  ]);
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 4", { exact: true })).toBeVisible();
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save PDF", exact: true }).click();
  await (await pending).saveAs("docs/private-samples/m2/browser-structure.pdf");
  const d = await PDFDocument.load(
    await readFile("docs/private-samples/m2/browser-structure.pdf"),
  );
  const layers = inspectLayers(d)!,
    tags = inspectTags(d)!;
  expect(layers.groups.length).toBe(2);
  expect(layers.enabled.length).toBe(1);
  expect(tags.parents.map((p) => p.page)).toEqual([1, 3]);
  expect(tags.nodes.size).toBe(4);
  await page
    .getByRole("button", { name: "Undo Combine PDFs", exact: true })
    .click();
  await expect(page.locator(".canvas-host canvas")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Redo Combine PDFs", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 4", { exact: true })).toBeVisible();
});

test("navigation inputs combine offline and saved output preserves targets", async ({
  page,
  context,
}) => {
  await open(page);
  await context.setOffline(true);
  await add(page, [
    "combine/navigation-b",
    "combine/navigation-a",
    "combine/navigation-b",
  ]);
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 9", { exact: true })).toBeVisible();
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save PDF", exact: true }).click();
  await (
    await pending
  ).saveAs("docs/private-samples/m2/browser-navigation.pdf");
  const doc = await PDFDocument.load(
    await readFile("docs/private-samples/m2/browser-navigation.pdf"),
  );
  const nav = inspectNavigation(doc);
  expect(nav.bookmarks.map((b) => b.destination!.page)).toEqual([2, 5, 8]);
  expect(nav.named.map((n) => n[1].page)).toEqual([2, 5, 8]);
  expect(nav.labels.map((l) => l[0])).toEqual([0, 2, 3, 5, 6, 8]);
});
test("COMBINE-01 mixed pages reorder offline, save and undo; no upload or automatic download", async ({
  page,
  context,
}) => {
  await open(page);
  await context.setOffline(true);
  const requests: string[] = [];
  page.on("request", (r) => {
    if (/^https?:/.test(r.url())) requests.push(r.url());
  });
  let downloads = 0;
  page.on("download", () => downloads++);
  await add(page, ["combine/a", "combine/b", "combine/c"]);
  await expect(
    page.getByText("3 files · 6 checked pages", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Move PDF 1 down", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Move PDF 3 up", exact: true })
    .click();
  await page.getByLabel("Combined PDF name").fill("合并/材料");
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 6", { exact: true })).toBeVisible();
  expect(downloads).toBe(0);
  await expect(page.locator(".page-text")).toContainText("B-1 searchable text");
  await page
    .getByRole("button", { name: "Preview page 4", exact: true })
    .click();
  await expect(page.locator(".page-text")).toContainText("C-1 searchable text");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save PDF", exact: true }).click();
  const d = await download;
  expect(d.suggestedFilename()).toBe("合并_材料.pdf");
  await mkdir("docs/private-samples/m2", { recursive: true });
  await d.saveAs("docs/private-samples/m2/browser-mixed.pdf");
  expect(
    (
      await PDFDocument.load(
        await readFile("docs/private-samples/m2/browser-mixed.pdf"),
      )
    ).getPageCount(),
  ).toBe(6);
  await page
    .getByRole("button", { name: "Undo Combine PDFs", exact: true })
    .click();
  await expect(page.locator(".canvas-host canvas")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Redo Combine PDFs", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 6", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Clear session", exact: true })
    .click();
  await page.getByRole("button", { name: "End session", exact: true }).click();
  expect(requests).toEqual([]);
  expect(
    await page.evaluate(async () => [
      localStorage.length,
      sessionStorage.length,
      (await indexedDB.databases()).length,
      (await caches.keys()).length,
    ]),
  ).toEqual([0, 0, 0, 0]);
});
test("COMBINE-03 bad input removable; same named inputs remain distinct", async ({
  page,
}) => {
  await open(page);
  await add(page, ["combine/a", "tagged"]);
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "tag tree has no structure children" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Apply combine", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Remove PDF 2", exact: true }).click();
  await add(page, ["combine/a"]);
  await expect(page.locator(".photo-list li")).toHaveCount(2);
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 4", { exact: true })).toBeVisible();
});
test("M1 to M2 uses current revision directly, draft switching and undo retain photos result", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page
    .getByRole("button", { name: "Turn Photos into PDF", exact: true })
    .click();
  await page
    .locator("#photo-files")
    .setInputFiles("tests/fixtures/photos/red.jpg");
  await page.getByRole("button", { name: "Apply photos", exact: true }).click();
  await expect(page.getByText("Page 1 of 1", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await expect(page.locator(".photo-list li")).toContainText("Photos.pdf");
  await add(page, ["combine/a"]);
  await page
    .getByRole("button", { name: "Turn Photos into PDF", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Unapplied combine changes" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Stay here", exact: true }).click();
  await expect(page.locator(".photo-list li")).toHaveCount(2);
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 3", { exact: true })).toBeVisible();
  await expect(page.locator(".photo-list li")).toHaveCount(1);
  await expect(page.locator(".photo-list li")).toContainText("Combined.pdf");
  await page
    .getByRole("button", { name: "Undo Combine PDFs", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 1", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Redo Combine PDFs", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 3", { exact: true })).toBeVisible();
});
for (const failure of ["cancel", "crash", "timeout"] as const)
  test(`combine ${failure} keeps previous document and input list`, async ({
    page,
  }) => {
    await open(page);
    await page.locator("#pdf-file").setInputFiles("tests/fixtures/plain.pdf");
    await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
    await page
      .getByRole("button", { name: "Combine PDFs", exact: true })
      .click();
    await expect(page.locator(".photo-list li")).toHaveCount(1);
    await add(page, ["combine/c"]);
    await page.evaluate((failure) => {
      const Native = Worker;
      window.Worker = class extends Native {
        postMessage(
          data: unknown,
          options?: Transferable[] | StructuredSerializeOptions,
        ) {
          if (
            data &&
            typeof data === "object" &&
            Reflect.get(data, "operation") === "combine"
          ) {
            if (failure === "crash")
              queueMicrotask(() =>
                this.dispatchEvent(
                  new ErrorEvent("error", { cancelable: true }),
                ),
              );
            return;
          }
          super.postMessage(
            data,
            Array.isArray(options) ? { transfer: options } : options,
          );
        }
      };
      const timer = window.setTimeout;
      window.setTimeout = ((
        handler: TimerHandler,
        delay?: number,
        ...args: unknown[]
      ) =>
        timer(
          handler,
          delay === 120000 && failure === "timeout" ? 100 : delay,
          ...args,
        )) as typeof window.setTimeout;
    }, failure);
    await page
      .getByRole("button", { name: "Apply combine", exact: true })
      .click();
    if (failure === "cancel")
      await page.getByRole("button", { name: "Cancel combine task" }).click();
    await expect(
      page.getByRole("alert").filter({
        hasText:
          failure === "timeout"
            ? "took too long"
            : failure === "crash"
              ? "task failed"
              : "Cancelled",
      }),
    ).toBeVisible();
    await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
    await expect(page.locator(".photo-list li")).toHaveCount(2);
  });

test("incomplete tagged current input is rejected; removal permits a valid batch", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page.locator("#pdf-file").setInputFiles("tests/fixtures/tagged.pdf");
  await expect(page.locator(".canvas-host canvas")).toBeVisible();
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "tag tree has no structure children" }),
  ).toBeVisible();
  await add(page, ["combine/a", "combine/b"]);
  await expect(
    page.getByRole("button", { name: "Apply combine", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Remove PDF 1", exact: true }).click();
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 5", { exact: true })).toBeVisible();
});
test("combine draft Apply-and-continue undo and redo branching use the latest revision", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page.locator("#pdf-file").setInputFiles("tests/fixtures/combine/a.pdf");
  await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await expect(page.locator(".photo-list li")).toHaveCount(1);
  await add(page, ["combine/b"]);
  await page
    .getByRole("button", { name: "Undo Open PDF", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Apply and continue", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Redo Combine PDFs", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Combine PDFs", exact: true }).click();
  await expect(page.locator(".photo-list li")).toHaveCount(1);
  await add(page, ["combine/c"]);
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Confirm that applying" }),
  ).toBeVisible();
  await page.getByRole("checkbox", { name: /Discard the redo branch/ }).check();
  await page
    .getByRole("button", { name: "Apply combine", exact: true })
    .click();
  await expect(page.getByText("Page 1 of 3", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Redo", exact: true }),
  ).toBeDisabled();
});
test("M2 controls fit 360px; empty and oversized batches cannot apply", async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await open(page);
  await expect(
    page.getByRole("button", { name: "Apply combine", exact: true }),
  ).toBeDisabled();
  const buffer = await readFile("tests/fixtures/combine/a.pdf");
  await page.locator("#combine-files").setInputFiles(
    Array.from({ length: 11 }, (_, i) => ({
      name: `same-${i}.pdf`,
      mimeType: "application/pdf",
      buffer,
    })),
  );
  await expect(
    page.getByRole("alert").filter({ hasText: "at most 10 PDFs" }),
  ).toBeVisible();
  await expect(page.locator(".photo-list li")).toHaveCount(0);
  await add(page, ["combine/a", "combine/b"]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "docs/evidence/m2-mobile-layout.png",
    fullPage: true,
  });
});
