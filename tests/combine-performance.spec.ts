import { test, expect } from "@playwright/test";
import { writeFile } from "node:fs/promises";
test("M2 100-page 20-MiB benchmark and 22 cleanups", async ({
  page,
  browser,
}) => {
  test.setTimeout(300000);
  await page.addInitScript(() => {
    const Native = Worker,
      workers = new Set<Worker>();
    window.Worker = class extends Native {
      constructor(url: string | URL, options?: WorkerOptions) {
        super(url, options);
        workers.add(this);
      }
      terminate() {
        workers.delete(this);
        super.terminate();
      }
    };
    Reflect.set(window, "__combineWorkers", () => workers.size);
  });
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  const samples: number[] = [];
  for (let n = 0; n < 22; n++) {
    await page
      .getByRole("button", { name: "Combine PDFs", exact: true })
      .click();
    await page
      .locator("#combine-files")
      .setInputFiles(
        Array.from(
          { length: 5 },
          (_, i) => `tests/fixtures/combine/benchmark-${i + 1}.pdf`,
        ),
      );
    await expect(
      page.getByText("5 files · 100 checked pages", { exact: true }),
    ).toBeVisible({ timeout: 30000 });
    const start = performance.now();
    await page
      .getByRole("button", { name: "Apply combine", exact: true })
      .click();
    await expect(page.getByText("Page 1 of 100", { exact: true })).toBeVisible({
      timeout: 30000,
    });
    if (n >= 2) samples.push(performance.now() - start);
    await page
      .getByRole("button", { name: "Clear session", exact: true })
      .click();
    await page
      .getByRole("button", { name: "End session", exact: true })
      .click();
    await expect
      .poll(() =>
        page.evaluate(() => Reflect.get(window, "__combineWorkers")()),
      )
      .toBe(0);
    await expect(page.locator(".canvas-host canvas")).toHaveCount(0);
  }
  const p95 = [...samples].sort((a, b) => a - b)[18]!;
  await writeFile(
    "docs/evidence/m2-performance.json",
    JSON.stringify(
      {
        environment: "Windows desktop",
        browser: browser.version(),
        inputFiles: 5,
        inputBytes: 20 * 1024 * 1024,
        pages: 100,
        warmups: 2,
        samples,
        p95Ms: p95,
        thresholdMs: 10000,
        clearCycles: 22,
        workersAfterEachClear: 0,
        fixtureNote:
          "Synthetic page-referenced comment padding, not realistic image complexity",
      },
      null,
      2,
    ),
  );
  expect(p95).toBeLessThanOrEqual(10000);
});
