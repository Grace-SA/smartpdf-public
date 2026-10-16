import { test, expect } from "@playwright/test";
test("M4 v2 phone harness completes all consent and split checks offline without submitting desktop evidence", async ({
  page,
}) => {
  test.setTimeout(240000);
  await page.goto("http://127.0.0.1:4201/__m4/check-v2");
  await expect(page.locator("#run")).toBeEnabled({ timeout: 30000 });
  await page.route(/^https?:/, (r) => r.abort());
  await page.locator("#offline").check();
  await page.locator("#run").click();
  await expect(page.locator("#results")).toContainText(
    '"harnessVersion": "m4-2"',
    { timeout: 210000 },
  );
  const report = JSON.parse((await page.locator("#results").textContent())!);
  expect(report.error, JSON.stringify(report.checks)).toBeUndefined();
  expect(report.checks.length).toBeGreaterThanOrEqual(17);
  expect(report.checks.every((r: { pass: boolean }) => r.pass)).toBe(true);
});
