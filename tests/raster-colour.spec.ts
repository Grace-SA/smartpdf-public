import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";

for (const format of ["JPG", "PNG"])
  test(`embedded linear ICC survives offline ${format} export`, async ({
    page,
    context,
    browserName,
  }) => {
    const unexpected: string[] = [];
    page.on("request", (r) => {
      if (/^https?:/.test(r.url()) && !r.url().startsWith("http://127.0.0.1:"))
        unexpected.push(r.url());
    });
    await page.goto("/pdf-to-jpg/");
    await page
      .locator("#pdf-file")
      .setInputFiles("tests/fixtures/raster-linear-icc.pdf");
    const submit = page.getByRole("button", {
      name: `Convert to ${format} →`,
      exact: true,
    });
    if (format === "PNG")
      await page
        .getByRole("radio", { name: "PNG Sharper text, larger files" })
        .check();
    await expect(submit).toBeEnabled();
    // Windows WebKit native-offline also blocks local blob workers and files.
    // Deny every HTTP request in both engines; Chromium also goes native-offline.
    await context.route(/^https?:/, (route) =>
      route.abort("internetdisconnected"),
    );
    if (browserName === "chromium") await context.setOffline(true);
    await submit.click();
    await expect(
      page.getByRole("heading", { name: "Your images are ready" }),
    ).toBeVisible();
    const download = page.waitForEvent("download");
    await page
      .getByRole("button", { name: `Download ${format}`, exact: true })
      .click();
    const content = await readFile((await (await download).path())!);
    const pixel = await page.evaluate(
      async ({ data, mime }) => {
        const image = new Image();
        image.src = `data:${mime};base64,${data}`;
        await image.decode();
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = 1;
        const ctx = canvas.getContext("2d")!;
        ctx.drawImage(image, -image.width / 2, -image.height / 2);
        return Array.from(ctx.getImageData(0, 0, 1, 1).data).slice(0, 3);
      },
      {
        data: content.toString("base64"),
        mime: format === "PNG" ? "image/png" : "image/jpeg",
      },
    );
    for (const value of pixel) {
      expect(value).toBeGreaterThan(175);
      expect(value).toBeLessThan(200);
    }
    expect(unexpected).toEqual([]);
  });
