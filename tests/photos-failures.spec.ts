import { test, expect } from "@playwright/test";
for (const kind of ["crash", "timeout"] as const) {
  test(`photo ${kind} preserves previous PDF and releases its worker`, async ({
    page,
  }) => {
    await page.addInitScript((kind) => {
      const Native = Worker,
        active = new Set<Worker>();
      window.Worker = class extends Native {
        constructor(url: string | URL, options?: WorkerOptions) {
          super(url, options);
          active.add(this);
        }
        terminate() {
          active.delete(this);
          super.terminate();
        }
        postMessage(
          data: unknown,
          options?: StructuredSerializeOptions | Transferable[],
        ) {
          if (data && typeof data === "object" && "inputs" in data) {
            if (kind === "crash")
              queueMicrotask(() =>
                this.dispatchEvent(
                  new ErrorEvent("error", {
                    message: "synthetic crash",
                    cancelable: true,
                  }),
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
      Reflect.set(window, "__workers", () => active.size);
      const timer = window.setTimeout;
      window.setTimeout = ((
        handler: TimerHandler,
        timeout?: number,
        ...args: unknown[]
      ) =>
        timer(
          handler,
          timeout === 120000 && Reflect.get(window, "__deadline")
            ? 100
            : timeout,
          ...args,
        )) as typeof window.setTimeout;
    }, kind);
    await page.goto("/");
    await expect(page.getByText("Ready for local processing")).toBeVisible();
    await page.locator("#pdf-file").setInputFiles("tests/fixtures/plain.pdf");
    await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
    await page
      .getByRole("button", { name: "Turn Photos into PDF", exact: true })
      .click();
    await page
      .locator("#photo-files")
      .setInputFiles("tests/fixtures/photos/red.jpg");
    await expect(
      page.getByRole("button", { name: "Apply photos", exact: true }),
    ).toBeEnabled();
    await page.getByRole("checkbox", { name: /Replace/ }).check();
    if (kind === "timeout")
      await page.evaluate(() => Reflect.set(window, "__deadline", true));
    await page
      .getByRole("button", { name: "Apply photos", exact: true })
      .click();
    await expect(
      page.getByRole("alert").filter({
        hasText: kind === "timeout" ? "took too long" : "could not be created",
      }),
    ).toBeVisible();
    await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
    await expect(page.locator(".photo-list li")).toHaveCount(1);
    await expect
      .poll(() => page.evaluate(() => Reflect.get(window, "__workers")()))
      .toBe(1);
    await page
      .getByRole("button", { name: "Clear session", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Discard changes", exact: true })
      .click();
    await expect
      .poll(() => page.evaluate(() => Reflect.get(window, "__workers")()))
      .toBe(0);
  });
}
test("cancelled download preserves the generated revision and supports saving again", async ({
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
  await expect(
    page.getByRole("button", { name: "Apply photos", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Apply photos", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Created 1 pages" }),
  ).toBeVisible();
  for (let n = 0; n < 2; n++) {
    const result = page.waitForEvent("download");
    await page.getByRole("button", { name: "Save PDF", exact: true }).click();
    await (await result).cancel();
    await expect(page.getByText("Page 1 of 1", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Save PDF", exact: true }),
    ).toBeEnabled();
  }
});
