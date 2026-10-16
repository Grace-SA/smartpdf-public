import { test, expect } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
test("frozen cohort actual offline split workflow", async ({
  page,
  context,
}) => {
  test.setTimeout(3600000);
  const folder =
    process.env.SMARTWORKS_M4_FOLDER ?? "docs/private-samples/m4-full";
  const origin = process.env.SMARTWORKS_M4_ORIGIN ?? "http://127.0.0.1:4186";
  const manifest = JSON.parse(
    await readFile(`${folder}/manifest.json`, "utf8"),
  );
  const prior = await readFile(`${folder}/browser.json`, "utf8")
    .then(JSON.parse)
    .catch(() => ({ rows: [], unexpectedRequests: 0 }));
  const rows: Record<string, unknown>[] = prior.rows;
  page.on("dialog", (dialog) => dialog.accept());
  let unexpectedRequests = prior.unexpectedRequests;
  await context.route("**/*", (route) => {
    const r = route.request();
    if (new URL(r.url()).origin !== origin || r.method() !== "GET") {
      unexpectedRequests++;
      return route.abort();
    }
    return route.continue();
  });
  for (const source of manifest.rows.filter(
    (r: { included: boolean }) => r.included,
  )) {
    if (rows.some((r) => r.id === source.id)) continue;
    await context.setOffline(false);
    await page.goto("/");
    await expect(page.getByText("Ready for local processing")).toBeVisible({
      timeout: 30000,
    });
    await context.setOffline(true);
    const row: Record<string, unknown> = {
      id: source.id,
      scenario: (source.currentPages ?? 1) > 1 ? "halves" : "single",
    };
    const start = performance.now();
    try {
      await page.locator("#pdf-file").setInputFiles(source.path);
      if (
        process.env.SMARTWORKS_M4_CONSENT === "1" &&
        ["W229", "W242"].includes(source.id)
      ) {
        await page
          .getByRole("button", {
            name: "Create copy without credentials",
            exact: true,
          })
          .click();
        row.preparation = "credentials";
      }
      await expect(page.locator(".canvas-host canvas")).toBeVisible({
        timeout: 20000,
      });
      row.sourcePreview = true;
      if (
        process.env.SMARTWORKS_M4_CONSENT === "1" &&
        ["W051", "W061", "W107", "W217"].includes(source.id)
      ) {
        await page
          .getByRole("button", {
            name: "Create ordinary PDF copy",
            exact: true,
          })
          .click();
        await page
          .getByRole("button", {
            name: "Create ordinary copy without standard claims",
            exact: true,
          })
          .click();
        await expect(
          page.getByText(/This new ordinary PDF does not claim/),
        ).toBeVisible();
        row.preparation = "ordinary";
      }
      const n = source.currentPages ?? 1,
        middle = Math.floor(n / 2);
      await page
        .getByRole("button", { name: "Split a PDF", exact: true })
        .click();
      await page
        .getByLabel("Page groups, one per line")
        .fill(n === 1 ? "1" : `1-${middle}\n${middle + 1}-${n}`);
      await page.getByLabel(/^Allow adjustment/).check();
      const create = page.getByRole("button", {
        name: "Create split results",
        exact: true,
      });
      if (await create.isDisabled()) {
        row.status = "preflight-refused";
      } else {
        const began = performance.now();
        await create.click();
        await expect
          .poll(
            async () => {
              if (await page.locator(".split-results li").count())
                return "done";
              if (await page.locator('.split-task [role="alert"]').count())
                return "refused";
              return "busy";
            },
            { timeout: 130000, intervals: [100, 250, 500] },
          )
          .not.toBe("busy");
        const count = await page.locator(".split-results li").count();
        row.splitMs = Math.round(performance.now() - began);
        row.status = count === (n === 1 ? 2 : 3) ? "published" : "refused";
        row.resultCount = count;
        if (count)
          await expect(
            page.getByText(`Page 1 of ${n}`, { exact: true }),
          ).toBeVisible();
      }
    } catch {
      row.status = row.sourcePreview ? "ui-error" : "preview-unavailable";
    }
    row.elapsedMs = Math.round(performance.now() - start);
    rows.push(row);
    await writeFile(
      `${folder}/browser.json`,
      JSON.stringify({ rows, unexpectedRequests }, null, 2),
    );
    // Every iteration starts fresh; acknowledge the app's generated-document exit guard.
  }
  expect(unexpectedRequests).toBe(0);
});
