import { createRequire } from "node:module";
import { resolve } from "node:path";
import { writeFile } from "node:fs/promises";
const require = createRequire(
  resolve(process.env.M13_DEPENDENCY_PACKAGE || "package.json"),
);
const { webkit, chromium } = require("@playwright/test");
const root = resolve(".research/m13");
const data = { tests: [], externalRequests: [], console: [] };
for (const [name, type] of process.env.M13_CASES
  ? [["webkit", webkit]]
  : [
      ["webkit", webkit],
      ["chromium", chromium],
    ]) {
  const browser = await type.launch({ headless: true });
  try {
    for (const fixture of process.env.M13_CASES?.split(",") ||
      (name === "webkit" ? ["cjk", "explicit-pages-table-image"] : ["cjk"])) {
      const context = await browser.newContext({ acceptDownloads: true });
      await context.route("**/*", (r) => {
        const u = r.request().url();
        if (
          u.startsWith("http://127.0.0.1:4243/") ||
          u.startsWith("blob:") ||
          u.startsWith("data:")
        )
          return r.continue();
        data.externalRequests.push(u);
        return r.abort();
      });
      const page = await context.newPage();
      page.on("console", (msg) => {
        if (["error", "warning"].includes(msg.type()))
          data.console.push({ name, message: msg.text().slice(0, 1000) });
      });
      page.on("pageerror", (e) =>
        data.console.push({ name, pageError: e.message }),
      );
      await page.goto(
        "http://127.0.0.1:4243/" +
          (process.env.M13_MEMORY ? "?memory=512" : ""),
      );
      await page.locator("#initialize").click();
      try {
        await page.waitForFunction(
          () =>
            /Ready|failed/.test(document.querySelector("#status").textContent),
          {},
          { timeout: 15000 },
        );
      } catch {
        data.tests.push({
          name,
          fixture,
          initializationTimedOut: true,
          status: await page.locator("#status").innerText(),
          metrics: await page.evaluate(() => window.research),
        });
        await context.close();
        continue;
      }
      const initial = await page.evaluate(() => window.research);
      console.log(name, fixture, "initialized", JSON.stringify(initial));
      const started = Date.now();
      await page
        .locator("#file")
        .setInputFiles(resolve(root, "fixtures", fixture + ".docx"));
      let timeout = false;
      try {
        await page.waitForFunction(
          () =>
            /Complete|failed/.test(
              document.querySelector("#status").textContent,
            ),
          {},
          { timeout: 15000 },
        );
      } catch {
        timeout = true;
      }
      const result = {
        name,
        fixture,
        initial,
        timeout,
        status: await page.locator("#status").innerText(),
        durationMs: Date.now() - started,
        metrics: await page.evaluate(() => window.research),
      };
      if (result.status === "Complete") {
        const promise = page.waitForEvent("download");
        await page.locator("#download").click();
        await (
          await promise
        ).saveAs(
          resolve(root, "outputs", name + "-diagnostic-" + fixture + ".pdf"),
        );
      }
      await page.locator("#cancel").click();
      try {
        await page
          .locator("#status")
          .filter({ hasText: "Released" })
          .waitFor({ timeout: 2000 });
        result.cancelReleased = true;
      } catch {
        result.cancelReleased = false;
      }
      data.tests.push(result);
      console.log(JSON.stringify(result));
      await context.close();
    }
  } finally {
    await browser.close();
    await writeFile(
      resolve(root, process.env.M13_REPORT || "diagnostics.json"),
      JSON.stringify(data, null, 2),
    );
  }
}
/* global console, process, document, window */
