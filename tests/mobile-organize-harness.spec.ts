import { test, expect } from "@playwright/test";
test("phone harness waits for asynchronous organize preflight before accessing rows", async ({
  page,
}) => {
  test.setTimeout(120000);
  await page.goto("http://127.0.0.1:4199/__m3/check?v=usability3");
  await expect(page.locator("#run")).toBeEnabled({ timeout: 30000 });
  // Deliberately delay the actual compatibility result to expose the old race.
  const app = page.frames().find((frame) => frame.parentFrame());
  await app!.evaluate(() => {
    const send = Worker.prototype.postMessage;
    Worker.prototype.postMessage = function (message, options) {
      if (message?.operation === "inspect") {
        setTimeout(
          () => send.call(this, message, options as StructuredSerializeOptions),
          250,
        );
      } else send.call(this, message, options as StructuredSerializeOptions);
    };
  });
  await page.route(/^https?:/, (route) => route.abort());
  await page.locator("#offline").check();
  await page.locator("#run").click();
  await expect(page.locator("#results")).toContainText(
    '"harnessVersion": "m3-usability-3"',
    { timeout: 110000 },
  );
  const report = JSON.parse((await page.locator("#results").textContent())!);
  expect(report.error).toBeUndefined();
  expect(report.checks.length).toBeGreaterThanOrEqual(16);
  expect(report.checks.every((check: { pass: boolean }) => check.pass)).toBe(
    true,
  );
  // Never submit a desktop report over the user's real phone report.
});
