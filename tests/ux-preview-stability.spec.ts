import { selectTool } from "./navigation";
import { test, expect } from "@playwright/test";
import { PDFDocument } from "pdf-lib";
import { readFile } from "node:fs/promises";
test.use({ trace: "off", screenshot: "off", video: "off" });
test("image and generated PDF previews stay stable while idle and after resize", async ({
  page,
}) => {
  await page.goto("/");
  await page.addStyleTag({
    content: ".page-detail-canvas::-webkit-scrollbar{width:17px;height:17px}",
  });
  await selectTool(page, "Turn Photos into PDF");
  await expect(page.locator("#photo-files")).toBeEnabled();
  // Prevent network transmission once local processing modules are ready.
  await page.route("**/*", (route) =>
    ["blob:", "data:"].includes(new URL(route.request().url()).protocol) ||
    new URL(route.request().url()).hostname === "127.0.0.1"
      ? route.continue()
      : route.abort(),
  );
  await page
    .locator("#photo-files")
    .setInputFiles(
      process.env.SMARTWORKS_LOCAL_IMAGE ||
        "docs/ux/public-synthetic-only/image-a.png",
    );
  await page
    .getByRole("button", { name: "Preview image 1", exact: true })
    .click();
  const image = page
    .getByRole("dialog", { name: "Image page preview" })
    .locator("img");
  await expect
    .poll(() => image.evaluate((e) => (e as HTMLImageElement).naturalWidth))
    .toBeGreaterThan(0);
  await page
    .getByRole("button", { name: "Close preview", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Convert to PDF →", exact: true })
    .click();
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF", exact: true }).click();
  const output = (await (await pending).path())!;
  await page
    .getByRole("button", { name: "Choose new files", exact: true })
    .click();
  await page.getByRole("button", { name: "← All tools", exact: true }).click();
  await selectTool(page, "Combine PDFs");
  await page.locator("#combine-files").setInputFiles({
    name: "generated.pdf",
    mimeType: "application/pdf",
    buffer: await readFile(output),
  });
  await page
    .getByRole("button", { name: "Preview PDF 1", exact: true })
    .click();

  const firstPageSize = (await PDFDocument.load(await readFile(output)))
    .getPage(0)
    .getSize();
  const host = page.locator(".page-detail-canvas");
  await expect(host.locator("canvas")).toHaveCount(1, { timeout: 30000 });
  for (const width of [1280, 1000, 390])
    for (const zoom of ["1", "0", "2"]) {
      await page
        .getByRole("combobox", { name: "Zoom", exact: true })
        .selectOption(zoom);
      await page.setViewportSize({ width, height: 900 });
      await page.waitForTimeout(100);
      await expect(page.locator(".lightbox-status")).toHaveCount(0, {
        timeout: 30000,
      });
      // A resize can finish after the previous render's status disappears.
      // Observe idleness only after the visible canvas matches this viewport.
      await expect
        .poll(() =>
          host.evaluate(
            (el, args) => {
              const box = el.getBoundingClientRect();
              const width = Math.round(box.width),
                height = Math.round(box.height);
              const widthScale =
                Math.max(100, width - (width < 640 ? 24 : 100)) / args.width;
              const scale =
                args.zoom === 0
                  ? Math.min(
                      widthScale,
                      Math.max(100, height - 24) / args.height,
                    )
                  : widthScale * args.zoom;
              const canvas = el.querySelector("canvas");
              return canvas
                ? Math.abs(parseFloat(canvas.style.width) - args.width * scale)
                : 9999;
            },
            { ...firstPageSize, zoom: Number(zoom) },
          ),
        )
        .toBeLessThan(1);
      await expect(page.locator(".lightbox-status")).toHaveCount(0);
      const changes = await host.evaluate(
        (el) =>
          new Promise<number>((resolve) => {
            let count = 0;
            const observer = new MutationObserver(
              (records) =>
                (count += records.filter((r) => r.type === "childList").length),
            );
            observer.observe(el, { childList: true });
            setTimeout(() => {
              observer.disconnect();
              resolve(count);
            }, 1800);
          }),
      );
      expect(
        changes,
        `idle canvas replacements at ${width}px / zoom ${zoom}`,
      ).toBe(0);
      await expect(host.locator("canvas")).toHaveCount(1);
    }
});
test("long file names preserve aligned metadata and actions", async ({
  page,
}, info) => {
  await page.goto("/");
  await selectTool(page, "Combine PDFs");
  const pdf = await PDFDocument.create();
  pdf.addPage([300, 400]);
  const buffer = Buffer.from(await pdf.save());
  await page
    .locator("#combine-files")
    .setInputFiles(
      ["Short.pdf", "GSD_Daily_Report_Example_Long_Filename_18124.pdf"].map(
        (name) => ({ name, mimeType: "application/pdf", buffer }),
      ),
    );
  await expect(page.locator(".merge-thumbnail img")).toHaveCount(2);
  for (const width of [1280, 1000, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const positions = await page
      .locator(".photo-list > li")
      .evaluateAll((nodes) =>
        nodes.map((el) => ({
          meta: el.querySelector("p")!.getBoundingClientRect().top,
          actions: el.querySelector(".card-actions")!.getBoundingClientRect()
            .top,
          bottom: el.getBoundingClientRect().bottom,
          actionBottom: el
            .querySelector(".card-actions")!
            .getBoundingClientRect().bottom,
        })),
      );
    expect(Math.abs(positions[0]!.meta - positions[1]!.meta)).toBeLessThan(2);
    expect(
      Math.abs(positions[0]!.actions - positions[1]!.actions),
    ).toBeLessThan(2);
    for (const p of positions)
      expect(p.actionBottom).toBeLessThanOrEqual(p.bottom);
    await page.screenshot({
      path: info.outputPath(`ux7-alignment-${info.project.name}-${width}.png`),
    });
  }
});
