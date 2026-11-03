import { test, expect, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { getDocument } from "pdfjs-dist/legacy/build/pdf.mjs";
import { selectToolPath } from "./navigation";

const ordinary = "tests/fixtures/m5/normal-a4.pdf",
  password = "Synthetic-M11-Only!";
const csp =
  "default-src 'self'; script-src 'self' 'wasm-unsafe-eval' https://static.cloudflareinsights.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' blob:; connect-src 'self' https://cloudflareinsights.com; worker-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'";
test.beforeEach(async ({ page }) => {
  // Match production policy, including the inline WASM and verifier workers.
  await page.route(/\/protect-pdf\/(?:\?.*)?$/, async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      headers: { ...response.headers(), "Content-Security-Policy": csp },
    });
  });
});
async function open(page: Page, path = ordinary) {
  await page.goto("/protect-pdf/");
  await page.locator("#pdf-file").setInputFiles(path);
  await expect(page.locator("#protect-password")).toBeVisible();
}
async function fill(page: Page, p = password) {
  await page.locator("#protect-password").fill(p);
  await page.locator("#protect-confirmation").fill(p);
}
async function create(page: Page, p = password) {
  await fill(page, p);
  await page.getByRole("button", { name: "Protect PDF", exact: true }).click();
  await expect(page.locator(".delivery")).toBeVisible();
  await expect(
    page.locator(
      ".protect-task,#protect-password,.task-notice-backdrop,[inert]",
    ),
  ).toHaveCount(0);
}
test("Protect enforces exact confirmation and displays no permissions panel", async ({
  page,
}) => {
  await open(page);
  const submit = page.getByRole("button", { name: "Protect PDF", exact: true });
  await expect(submit).toBeDisabled();
  await fill(page, "short");
  await expect(submit).toBeDisabled();
  await page.locator("#protect-password").fill(password);
  await expect(submit).toBeDisabled();
  await expect(
    page.getByText("Passwords do not match.", { exact: true }),
  ).toBeVisible();
  await fill(page);
  await expect(submit).toBeEnabled();
  await page
    .getByRole("button", { name: "Show passwords", exact: true })
    .click();
  await expect(page.locator("#protect-password")).toHaveAttribute(
    "type",
    "text",
  );
  await page
    .getByRole("button", { name: "Hide passwords", exact: true })
    .click();
  await expect(page.locator("#protect-confirmation")).toHaveAttribute(
    "type",
    "password",
  );
  await expect(
    page.getByText("Anyone with the password can read, copy or print", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(
    page.locator(".protect-task input[type=checkbox],.tool-faq"),
  ).toHaveCount(0);
  await page.locator("#protect-password").fill("sample-e\u0301-123");
  await page.locator("#protect-confirmation").fill("sample-é-123");
  await expect(submit).toBeDisabled();
});
test("Protect downloads a verified encrypted PDF and clears the editor", async ({
  page,
}) => {
  await open(page);
  await create(page);
  await expect(
    page.getByRole("heading", {
      name: "Your protected PDF is ready",
      exact: true,
    }),
  ).toBeFocused();
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF", exact: true }).click();
  const download = await pending,
    bytes = new Uint8Array(await readFile((await download.path())!));
  expect(download.suggestedFilename()).toBe("normal-a4-protected.pdf");
  for (const p of ["", "wrong", password]) {
    const task = getDocument({
      data: bytes.slice(),
      password: p,
      verbosity: 0,
    });
    try {
      if (p === password) expect((await task.promise).numPages).toBe(2);
      else
        await expect(task.promise).rejects.toMatchObject({
          name: "PasswordException",
        });
    } finally {
      await task.destroy();
    }
  }
});
for (const target of ["new", "split-pdf", "merge-pdf"]) {
  test(`Protect completion → ${target} opens a working native file chooser`, async ({
    page,
  }) => {
    await open(page);
    await create(page);
    if (target === "new")
      await page.getByRole("button", { name: /Choose new files/ }).click();
    else await selectToolPath(page, target);
    const pending = page.waitForEvent("filechooser");
    await page
      .locator(target === "merge-pdf" ? "#combine-files" : "#pdf-file")
      .click();
    await (await pending).setFiles([]);
    await expect(page.locator("[inert],dialog[open]")).toHaveCount(0);
  });
}
test("Protect replaces and leaves through two clear choices with cleared credentials", async ({
  page,
}) => {
  await open(page);
  await fill(page);
  await page
    .getByRole("button", { name: "Choose another file", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Leave this task?" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Keep editing", exact: true }).click();
  await expect(page.locator("#protect-password")).toHaveValue(password);
  await selectToolPath(page, "split-pdf");
  await page
    .getByRole("button", { name: "Discard task and leave", exact: true })
    .click();
  await expect(page.locator("#protect-password")).toHaveCount(0);
  await selectToolPath(page, "protect-pdf");
  await expect(page.locator("#pdf-file")).toHaveValue("");
  await expect(page.locator("[inert],dialog[open]")).toHaveCount(0);
});
for (const name of [
  "encrypted",
  "corrupted",
  "zero-pages",
  "large-50mb",
  "100mb",
]) {
  test(`Protect safely refuses ${name} before requesting a password`, async ({
    page,
  }) => {
    await page.goto("/protect-pdf/");
    await page
      .locator("#pdf-file")
      .setInputFiles(`tests/fixtures/m5/${name}.pdf`);
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.locator("#protect-password,.delivery")).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Try again", exact: true }),
    ).toHaveCount(0);
  });
}
test("Protect completes offline once public resources are ready", async ({
  page,
  context,
}) => {
  await page.goto("/protect-pdf/");
  await expect(page.locator(".status.ready")).toBeAttached();
  await context.setOffline(true);
  try {
    await page.locator("#pdf-file").setInputFiles(ordinary);
    await expect(page.locator("#protect-password")).toBeVisible();
    await create(page);
  } finally {
    await context.setOffline(false);
  }
});
test("Protect private names and passwords stay out of requests, logs and storage", async ({
  page,
  context,
}) => {
  const p = "synthetic-secret-marker-123",
    name = "synthetic-private-marker.pdf",
    requests: string[] = [],
    logs: string[] = [];
  context.on("request", (request) =>
    requests.push(request.url() + " " + (request.postData() ?? "")),
  );
  page.on("console", (message) => logs.push(message.text()));
  await page.goto("/protect-pdf/");
  await page.locator("#pdf-file").setInputFiles({
    name,
    mimeType: "application/pdf",
    buffer: await readFile(ordinary),
  });
  await expect(page.locator("#protect-password")).toBeVisible();
  await create(page, p);
  const storage = await page.evaluate(async () => ({
    local: { ...localStorage },
    session: { ...sessionStorage },
    db: (await indexedDB.databases()).map((item) => item.name),
  }));
  for (const output of [
    JSON.stringify(requests),
    JSON.stringify(logs),
    JSON.stringify(storage),
  ]) {
    expect(output).not.toContain(p);
    expect(output).not.toContain(name);
  }
});
test("Protect narrow and landscape layouts maintain clear actions and readable fields", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page);
  for (const size of [
    { width: 320, height: 700 },
    { width: 390, height: 844 },
    { width: 844, height: 390 },
    { width: 1280, height: 900 },
  ]) {
    await page.setViewportSize(size);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await expect(page.locator("#protect-password")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Protect PDF", exact: true }),
    ).toBeVisible();
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: info.outputPath("protect-mobile.png"),
    fullPage: true,
  });
  await create(page);
  await page.screenshot({
    path: info.outputPath("protect-complete-mobile.png"),
    fullPage: true,
  });
});
test("Protect handles engine failure with secret clearing and a fresh successful retry", async ({
  page,
}) => {
  await open(page);
  await fill(page);
  // A worker-level error must not leak its raw diagnostic or retain fields.
  await page.evaluate(() => {
    const Native = Worker;
    window.Worker = class extends Native {
      constructor(...args: ConstructorParameters<typeof Worker>) {
        super(...args);
        queueMicrotask(() => this.dispatchEvent(new Event("error")));
      }
    };
    Object.assign(window, {
      restoreProtectWorker: () => {
        window.Worker = Native;
      },
    });
  });
  await page.getByRole("button", { name: "Protect PDF", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "could not finish safely",
  );
  await expect(page.locator("#protect-password")).toHaveValue("");
  await expect(page.locator("#protect-confirmation")).toHaveValue("");
  await page.evaluate(() => {
    (
      window as unknown as { restoreProtectWorker: () => void }
    ).restoreProtectWorker();
  });
  await create(page);
});
test("Protect cancels a stalled private worker and releases all interaction locks", async ({
  page,
}) => {
  await open(page);
  await fill(page);
  await page.evaluate(() => {
    const Native = Worker;
    window.Worker = class extends Native {
      postMessage() {
        /* synthetic stalled engine */
      }
    };
    Object.assign(window, {
      restoreProtectWorker: () => {
        window.Worker = Native;
      },
    });
  });
  await page.getByRole("button", { name: "Protect PDF", exact: true }).click();
  await page
    .getByRole("button", { name: "Cancel processing", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("cancelled");
  await expect(page.locator("#protect-password")).toHaveValue("");
  await expect(page.locator("[inert],.task-notice-backdrop")).toHaveCount(0);
  await page.evaluate(() => {
    (
      window as unknown as { restoreProtectWorker: () => void }
    ).restoreProtectWorker();
  });
  await create(page);
});
test("Protect 200 pages completes within the bounded local workflow", async ({
  page,
}) => {
  await open(page, "tests/fixtures/m5/200-pages.pdf");
  await create(page);
  await expect(page.locator(".output-summary")).toContainText("200 pages");
});
test("Protect prepares silently without moving or disabling its native picker", async ({
  page,
}) => {
  let release!: () => void;
  const barrier = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/qpdf.wasm", async (route) => {
    await barrier;
    await route.continue().catch(() => {});
  });
  await page.goto("/protect-pdf/");
  const label = page.locator('label[for="pdf-file"]'),
    input = page.locator("#pdf-file");
  await expect(input).toBeEnabled();
  await expect(page.locator(".panel > .status")).toBeHidden();
  const before = await label.boundingBox();
  const pending = page.waitForEvent("filechooser");
  await label.click();
  await (await pending).setFiles([]);
  release();
  await expect(page.locator(".status.ready")).toBeAttached();
  const after = await label.boundingBox();
  expect(Math.abs(after!.y - before!.y)).toBeLessThanOrEqual(1);
});
