import { test, expect } from "@playwright/test";
test("M4 phone harness completes offline without submitting desktop evidence", async ({
  page,
}) => {
  test.setTimeout(180000);
  await page.goto("http://127.0.0.1:4199/__m4/check?v=m4-1");
  await expect(page.locator("#run")).toBeEnabled({ timeout: 30000 });
  await page.route(/^https?:/, (route) => route.abort());
  await page.locator("#offline").check();
  await page.locator("#run").click();
  await expect(page.locator("#results")).toContainText(
    '"harnessVersion": "m4-1"',
    { timeout: 150000 },
  );
  const report = JSON.parse((await page.locator("#results").textContent())!);
  expect(report.error).toBeUndefined();
  expect(report.checks.length).toBeGreaterThanOrEqual(10);
  expect(report.checks.every((check: { pass: boolean }) => check.pass)).toBe(
    true,
  );
});
