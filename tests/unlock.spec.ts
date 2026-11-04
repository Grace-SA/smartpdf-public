import { test, expect, type Page } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { PDFDocument } from "pdf-lib";
import { selectToolPath } from "./navigation";
const fixtures = "tests/fixtures/m12/";
async function open(page: Page, name = "aes-256") {
  await page.goto("/unlock-pdf/");
  await page.locator("#pdf-file").setInputFiles(fixtures + name + ".pdf");
  await expect(
    page.getByRole("button", { name: "Unlock PDF", exact: true }),
  ).toBeVisible();
}
async function create(page: Page, password = "synthetic-user") {
  if (await page.locator("#unlock-password").count())
    await page.locator("#unlock-password").fill(password);
  await page.getByRole("button", { name: "Unlock PDF", exact: true }).click();
  await expect(page.locator(".delivery")).toBeVisible();
  await expect(page.locator(".unlock-task")).toHaveCount(0);
  await expect(page.locator("#unlock-password")).toHaveCount(0);
}
for (const name of [
  "rc4-40",
  "rc4-128",
  "aes-128",
  "aes-256",
  "r5",
  "unicode",
  "legacy-encoding",
  "special",
  "empty-user",
])
  test(`Unlock ${name} locally and end the task`, async ({ page }) => {
    await open(page, name);
    const password =
      name === "unicode"
        ? "合成 密碼✓"
        : name === "legacy-encoding"
          ? "é space"
          : name === "special"
            ? "  \"quote'=合成✓  "
            : name === "empty-user"
              ? ""
              : "synthetic-user";
    await create(page, password);
    await expect(
      page.getByRole("heading", { name: "Your unlocked PDF is ready" }),
    ).toBeVisible();
    const pending = page.waitForEvent("download");
    await page
      .getByRole("button", { name: "Download PDF", exact: true })
      .click();
    const download = await pending;
    const bytes = await readFile((await download.path())!);
    const doc = await PDFDocument.load(bytes);
    expect(doc.context.trailerInfo.Encrypt).toBeUndefined();
    expect(doc.getPageCount()).toBe(2);
    await writeFile(test.info().outputPath("synthetic-unlocked.pdf"), bytes);
  });
test("Unlock accepts owner access and retains the source after a wrong password", async ({
  page,
}) => {
  await open(page);
  await page.locator("#unlock-password").fill("incorrect-synthetic");
  await page.getByRole("button", { name: "Unlock PDF", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "That password didn't open",
  );
  await expect(page.locator(".unlock-file strong")).toHaveText("aes-256.pdf");
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(page.locator("#unlock-password")).toHaveAttribute(
    "type",
    "text",
  );
  await page.getByRole("button", { name: "Hide password" }).click();
  await expect(page.locator("#unlock-password")).toHaveAttribute(
    "type",
    "password",
  );
  await page.locator("#unlock-password").fill("synthetic-owner");
  await page.locator("#unlock-password").press("Enter");
  await expect(page.locator(".delivery")).toBeVisible();
});
test("Unlock never reports success for a PDF that is already unencrypted", async ({
  page,
}) => {
  await page.goto("/unlock-pdf/");
  await page
    .locator("#pdf-file")
    .setInputFiles("tests/fixtures/m5/normal-a4.pdf");
  await expect(
    page.getByRole("heading", { name: "No unlocking needed" }),
  ).toBeVisible();
  await expect(page.locator(".delivery")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Unlock PDF", exact: true }),
  ).toHaveCount(0);
  await expect(page.locator("#unlock-password")).toHaveCount(0);
  await page.getByRole("button", { name: "Choose another file" }).click();
  await expect(page.locator("#pdf-file")).toHaveValue("");
});
for (const name of ["handler", "revision"])
  test(`Unlock explains unsupported ${name} without asking for a password`, async ({
    page,
  }) => {
    await page.goto("/unlock-pdf/");
    await page.locator("#pdf-file").setInputFiles(fixtures + name + ".pdf");
    await expect(page.getByRole("alert")).toContainText("protection method");
    await expect(page.locator("#unlock-password")).toHaveCount(0);
  });
for (const name of ["signature", "credentials"])
  test(`Unlock refuses ${name} and retains no password after refusal`, async ({
    page,
  }) => {
    await open(page, name);
    await page.locator("#unlock-password").fill("synthetic-user");
    await page.getByRole("button", { name: "Unlock PDF", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText(
      "digital signature or Content Credentials",
    );
    await expect(page.locator("#unlock-password")).toHaveCount(0);
    await expect(page.locator(".delivery")).toHaveCount(0);
  });
test("Unlock standard copy requires explicit confirmation", async ({
  page,
}) => {
  await open(page, "standard");
  await page.locator("#unlock-password").fill("synthetic-user");
  await page.getByRole("button", { name: "Unlock PDF", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "Create an ordinary PDF copy" }),
  ).toBeVisible();
  await expect(page.locator(".delivery")).toHaveCount(0);
  await page.getByRole("button", { name: "Keep this task" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Unlock PDF", exact: true }).click();
  await page
    .getByRole("button", { name: "Create ordinary unlocked PDF" })
    .click();
  await expect(page.locator(".delivery")).toBeVisible();
});
for (const destination of ["new", "/split-pdf/", "/merge-pdf/"])
  test(`Unlock completion ${destination} opens an empty functional picker`, async ({
    page,
  }) => {
    await open(page);
    await create(page);
    if (destination === "new")
      await page
        .getByRole("button", { name: "Choose new files", exact: true })
        .click();
    else
      await selectToolPath(
        page,
        destination.replace(/^\//, "").replace(/\/$/, ""),
      );
    const input = page.locator(
      destination === "/merge-pdf/" ? "#combine-files" : "#pdf-file",
    );
    await expect(input).toHaveValue("");
    const chooser = page.waitForEvent("filechooser");
    await input.click();
    await (await chooser).setFiles([]);
    await expect(page.locator("[inert],dialog[open]")).toHaveCount(0);
  });
test("Unlock departure has two clear choices and discards credentials", async ({
  page,
}) => {
  await open(page);
  await page.locator("#unlock-password").fill("synthetic-user");
  await selectToolPath(page, "split-pdf");
  await expect(
    page.getByRole("dialog", { name: "Leave this task?" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Keep editing", exact: true }).click();
  await expect(page.locator("#unlock-password")).toHaveValue("synthetic-user");
  await selectToolPath(page, "split-pdf");
  await page
    .getByRole("button", { name: "Discard task and leave", exact: true })
    .click();
  await expect(page.locator("#unlock-password")).toHaveCount(0);
  await expect(page.locator("#pdf-file")).toHaveValue("");
});
test("Unlock processing and retry keep passwords out of requests, logs and storage", async ({
  page,
  context,
}) => {
  const marker = "private-synthetic-marker";
  const outbound: string[] = [],
    consoleMessages: string[] = [];
  context.on("request", (r) =>
    outbound.push(r.url() + " " + (r.postData() ?? "")),
  );
  page.on("console", (m) => consoleMessages.push(m.text()));
  await open(page);
  await page.locator("#unlock-password").fill(marker);
  await page.getByRole("button", { name: "Unlock PDF", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "That password didn't open",
  );
  const stored = await page.evaluate(() =>
    JSON.stringify({
      local: { ...localStorage },
      session: { ...sessionStorage },
      url: location.href,
    }),
  );
  expect(outbound.join("\n")).not.toContain(marker);
  expect(consoleMessages.join("\n")).not.toContain(marker);
  expect(stored).not.toContain(marker);
  const allowedOrigin = new URL(page.url()).origin;
  expect(
    outbound.some((record) => {
      const url = record.split(" ")[0]!;
      return /^https?:\/\//.test(url) && new URL(url).origin !== allowedOrigin;
    }),
  ).toBe(false);
  await create(page);
  await expect(page.locator(".delivery")).toBeVisible();
});
for (const name of ["large-50mb", "100mb"])
  test(`Unlock refuses ${name} before loading document data into a worker`, async ({
    page,
  }) => {
    await page.goto("/unlock-pdf/");
    await page
      .locator("#pdf-file")
      .setInputFiles("tests/fixtures/m5/" + name + ".pdf");
    await expect(page.getByRole("alert")).toContainText(
      "local processing limits",
    );
    await expect(page.locator("#unlock-password")).toHaveCount(0);
    await page.getByRole("button", { name: "Choose another file" }).click();
    const chooser = page.waitForEvent("filechooser");
    await page.locator("#pdf-file").click();
    await (await chooser).setFiles([]);
  });
test("Unlock can cancel while public engine preparation is pending", async ({
  page,
}) => {
  const wasm = await readFile("public/qpdf.wasm");
  let release: (() => Promise<void>) | undefined;
  await page.route(
    "**/qpdf.wasm",
    (route) =>
      new Promise<void>((resolve) => {
        release = async () => {
          await route.fulfill({
            status: 200,
            contentType: "application/wasm",
            body: wasm,
          });
          resolve();
        };
      }),
  );
  await page.goto("/unlock-pdf/");
  await page.locator("#pdf-file").setInputFiles(fixtures + "aes-256.pdf");
  await page.getByRole("button", { name: "Cancel checking" }).click();
  await expect(page.getByRole("alert")).toContainText("cancelled");
  await expect(
    page.getByRole("button", { name: "Try again", exact: true }),
  ).toBeVisible();
  await release!();
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(page.locator("#unlock-password")).toBeVisible();
  await create(page);
});
test("Unlock reports a bad engine resource and can retry after restoration", async ({
  page,
}) => {
  await page.route("**/qpdf.wasm", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/wasm",
      body: "not-wasm",
    }),
  );
  await page.goto("/unlock-pdf/");
  await page.locator("#pdf-file").setInputFiles(fixtures + "aes-256.pdf");
  await expect(page.getByRole("alert")).toContainText(
    "Local processing couldn't finish",
  );
  await page.unroute("**/qpdf.wasm");
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(page.locator("#unlock-password")).toBeVisible();
  await create(page);
});
test("Unlock 200 pages preserves every page in the completed download", async ({
  page,
}) => {
  await open(page, "reg-200-pages");
  await create(page);
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF", exact: true }).click();
  const download = await pending;
  expect(
    (
      await PDFDocument.load(await readFile((await download.path())!))
    ).getPageCount(),
  ).toBe(200);
});
test("Unlock completes offline after its public engine is ready", async ({
  page,
  context,
}) => {
  await page.goto("/unlock-pdf/");
  await expect(page.locator(".status.ready")).toBeAttached();
  await context.setOffline(true);
  try {
    await page.locator("#pdf-file").setInputFiles(fixtures + "aes-256.pdf");
    await expect(page.locator("#unlock-password")).toBeVisible();
    await create(page);
  } finally {
    await context.setOffline(false);
  }
});
test("Unlock narrow and landscape layouts keep a single focused operation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page);
  await expect(page.locator(".tool-faq")).toHaveCount(0);
  for (const size of [
    { width: 390, height: 844 },
    { width: 320, height: 700 },
    { width: 844, height: 390 },
  ]) {
    await page.setViewportSize(size);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await expect(page.locator("#unlock-password")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Unlock PDF", exact: true }),
    ).toBeEnabled({ enabled: false });
  }
  await page.locator("#unlock-password").fill("synthetic-user");
  await page.setViewportSize({ width: 390, height: 844 });
  await create(page);
});
test("Unlock long file names keep readable width on narrow phones", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/unlock-pdf/");
  await page.locator("#pdf-file").setInputFiles({
    name: "Synthetic long document name for privacy and layout validation.pdf",
    mimeType: "application/pdf",
    buffer: await readFile(fixtures + "aes-256.pdf"),
  });
  await expect(page.locator("#unlock-password")).toBeVisible();
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    const file = page.locator(".unlock-file > div");
    const bounds = await file.boundingBox();
    expect(bounds!.width).toBeGreaterThan(width * 0.45);
    const header = await page.locator(".unlock-file").boundingBox();
    expect(header!.height).toBeLessThan(240);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await create(page);
});
test("Unlock prepares silently without moving or disabling the native picker", async ({
  page,
}) => {
  const engine = await readFile("public/qpdf.wasm");
  let release: (() => Promise<void>) | undefined;
  await page.route(
    "**/qpdf.wasm",
    (route) =>
      new Promise<void>((resolve) => {
        release = async () => {
          await route.fulfill({
            status: 200,
            contentType: "application/wasm",
            body: engine,
          });
          resolve();
        };
      }),
  );
  await page.goto("/unlock-pdf/");
  const input = page.locator("#pdf-file");
  await expect(input).toBeVisible();
  await expect(input).toBeEnabled();
  const before = await input.boundingBox();
  const picker = page.waitForEvent("filechooser");
  await input.click();
  await (await picker).setFiles([]);
  await expect.poll(() => !!release).toBe(true);
  await release!();
  await expect(page.locator(".status.ready")).toBeAttached();
  const after = await input.boundingBox();
  expect(Math.abs(before!.y - after!.y)).toBeLessThanOrEqual(0.5);
  expect(Math.abs(before!.height - after!.height)).toBeLessThanOrEqual(0.5);
  expect(await page.locator("body").innerText()).not.toMatch(
    /Opening this tool|Preparing local processing|tools are getting ready/i,
  );
});
test("Unlock excessive compressed objects fail safely and a normal next task still works", async ({
  page,
}) => {
  await open(page, "dense");
  await page.locator("#unlock-password").fill("synthetic-user");
  await page.getByRole("button", { name: "Unlock PDF", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "local processing limits",
  );
  await expect(page.locator(".delivery")).toHaveCount(0);
  await page.getByRole("button", { name: "Choose another file" }).click();
  await page.locator("#pdf-file").setInputFiles(fixtures + "aes-256.pdf");
  await expect(page.locator("#unlock-password")).toBeVisible();
  await create(page);
});
