// Synthetic result rendering only; this is not a real conversion smoke test.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { chromium, webkit } from "@playwright/test";

const files = new Map([
  ["/", ["index.html", "text/html"]],
  ["/app.js", ["app.js", "text/javascript"]],
  ["/style.css", ["style.css", "text/css"]],
]);
const server = createServer(async (request, response) => {
  const file = files.get(request.url);
  if (!file) {
    response.writeHead(404).end();
    return;
  }
  try {
    const data = await readFile(new URL(`../web/${file[0]}`, import.meta.url));
    response.writeHead(200, { "Content-Type": file[1] }).end(data);
  } catch {
    response.writeHead(500).end();
  }
});
await new Promise((resolve, reject) => {
  server.once("error", reject);
  server.listen(0, "127.0.0.1", resolve);
});
const base = `http://127.0.0.1:${server.address().port}`;
try {
  for (const [name, engine] of [
    ["chromium", chromium],
    ["webkit", webkit],
  ]) {
    const browser = await engine.launch({ headless: true });
    try {
      const page = await browser.newPage();
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.route("**/api/capabilities", (route) =>
        route.fulfill({
          json: { editable_available: true, retention_seconds: 3600 },
        }),
      );
      let state = {
        state: "needs_review",
        mode: "editable",
        report: {
          assistance: {
            pages: [
              {
                page: 1,
                route: "native-coordinate",
                text_granularity: "word",
                warnings: [],
              },
              {
                page: 2,
                route: "native-coordinate",
                text_granularity: "word",
                warnings: ["table_rebuilt_as_positioned_text"],
              },
              { page: 3, route: "stirling-table" },
              { page: 4, route: "native-regions", editable_runs: 7 },
              {
                page: 5,
                route: "paddle-ocr",
                editable_lines: 1,
                detected_lines: 3,
              },
              { page: 6, route: "source-image-fallback" },
            ],
          },
        },
      };
      await page.route("**/api/jobs/synthetic-report", (route) =>
        route.fulfill({ json: state }),
      );
      await page.goto(base);
      await page.evaluate(
        "job = { id: 'synthetic-report', token: 'synthetic-only' }; poll(generation)",
      );
      const details = await page.locator("#page-review li").allTextContents();
      assert.equal(details.length, 6);
      for (const detail of details.slice(0, 2)) {
        assert.match(detail, /Text is editable in separate text boxes/);
        assert.match(detail, /Tables are not editable as cells/);
      }
      assert.match(details[2], /Check table rows, columns and merged cells/);
      assert.doesNotMatch(details[2], /not editable as cells/);
      assert.match(details[3], /7 text runs are editable/);
      assert.match(details[4], /1 of 3 detected text lines are editable/);
      assert.match(details[5], /This page is not editable/);
      assert.match(
        await page.locator("#status").innerText(),
        /review required/,
      );
      state = { state: "ready", mode: "preserve" };
      await page.evaluate("poll(generation)");
      assert.equal(await page.locator("#page-review li").count(), 0);
      assert.match(
        await page.locator("#status").innerText(),
        /text and objects are not editable/,
      );
      assert.deepEqual(errors, []);
      console.log(
        `${name}: editable text, table semantics, partial OCR and preserve reports passed`,
      );
    } finally {
      await browser.close();
    }
  }
} finally {
  await new Promise((resolve) => server.close(resolve));
}
