import { expect, test, type Page } from "@playwright/test";
import { selectToolPath } from "./navigation";
import { publicTools, toolCatalog } from "../src/routes";

const tools = publicTools.map(
  (tool) =>
    [
      toolCatalog[tool].path.replace(/^\//, "").replace(/\/$/, ""),
      tool === "pdfword"
        ? "pdfword-file"
        : tool === "excel"
          ? "excel-file"
          : tool === "word"
            ? "word-file"
            : tool === "ppt"
              ? "ppt-file"
              : tool === "combine"
                ? "combine-files"
                : tool === "photos"
                  ? "photo-files"
                  : "pdf-file",
    ] as const,
);
const cloudTools = tools.filter(([path]) =>
  ["word-to-pdf", "powerpoint-to-pdf", "excel-to-pdf", "pdf-to-word"].includes(
    path,
  ),
);
const localTools = tools.filter(
  ([path]) => !cloudTools.some(([cloud]) => path === cloud),
);

test("cloud navigation stops pending local workers before document exit", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => {
    const NativeWorker = window.Worker;
    const live = new Set<Worker>();
    window.Worker = class extends NativeWorker {
      constructor(url: string | URL, options?: WorkerOptions) {
        super(url, options);
        live.add(this);
        // Hold the real worker's ready packet to exercise an in-flight boot.
        this.addEventListener(
          "message",
          (event) => {
            if (event.data?.ready === true) event.stopImmediatePropagation();
          },
          { capture: true },
        );
        document.documentElement.setAttribute("data-audit-worker", "pending");
      }
      terminate() {
        live.delete(this);
        super.terminate();
      }
    };
    window.addEventListener("pagehide", () =>
      sessionStorage.setItem("synthetic-worker-exit", String(live.size)),
    );
  });
  await page.goto("/merge-pdf/");
  await expect(page.locator("html")).toHaveAttribute(
    "data-audit-worker",
    "pending",
  );
  await expect(page.locator("#combine-files")).toBeEnabled();
  await selectToolPath(page, "powerpoint-to-pdf");
  await expect(page.locator("#ppt-file")).toBeVisible();
  expect(
    await page.evaluate(() => sessionStorage.getItem("synthetic-worker-exit")),
  ).toBe("0");
  expect(errors).toEqual([]);
});

async function checkPicker(page: Page, id: string) {
  const input = page.locator(`#${id}`);
  await expect(input).toBeVisible();
  await expect(input).toBeEnabled();
  await expect(page.locator(".panel > .status")).toBeHidden();
  await expect(page.locator(".tool-loading")).toHaveCount(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const picker = page.waitForEvent("filechooser", { timeout: 5_000 });
  await page.locator(`label[for="${id}"]`).tap();
  await (await picker).setFiles([]);
  await expect(input).toHaveValue("");
}

async function navigate(page: Page, path: string) {
  await selectToolPath(page, path);
}

for (const width of [390, 1280]) {
  test(`${width}: every tool-to-tool transition keeps the real picker responsive`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 844 });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("/");
    for (const [source] of localTools) {
      await navigate(page, source);
      for (const [target, id] of localTools) {
        await navigate(page, target);
        await expect(page).toHaveURL(new RegExp(`/${target}/$`));
        await checkPicker(page, id);
        await navigate(page, source);
      }
      await page.getByText("← All tools", { exact: true }).tap();
      await expect(page.locator(".tool-home")).toBeVisible();
      await expect(page.locator(".tool-home [role=status]")).toHaveCount(0);
    }
    expect(errors).toEqual([]);
  });

  test(`${width}: every local tool exchanges a working picker with cloud converters`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 844 });
    const errors: string[] = [];
    let phase = "opening cloud page";
    page.on("pageerror", (error) =>
      errors.push(`${phase}: ${error.stack || error.message}`),
    );
    for (const [cloudPath, cloudPicker] of cloudTools) {
      await page.goto(`/${cloudPath}/`);
      for (const [path, id] of localTools) {
        phase = `${cloudPath} -> ${path}`;
        await navigate(page, path);
        await expect(page).toHaveURL(new RegExp(`/${path}/$`));
        await checkPicker(page, id);
        phase = `${path} -> ${cloudPath}`;
        await navigate(page, cloudPath);
        await expect(page).toHaveURL(new RegExp(`/${cloudPath}/$`));
        await checkPicker(page, cloudPicker);
      }
    }
    await page.getByText("← All tools", { exact: true }).tap();
    await expect(page.locator(".tool-home")).toBeVisible();
    expect(errors).toEqual([]);
  });
}

test("rapid navigation while cold resources are delayed leaves only the latest tool active", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let release!: () => void;
  const barrier = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/pdf-resources.json", async (route) => {
    await barrier;
    await route.continue().catch(() => {});
  });
  await page.goto("/");
  for (const [path, id] of tools) {
    await selectToolPath(page, path);
    await checkPicker(page, id);
  }
  release();
  await expect(page.locator(".status.ready")).toBeAttached();
  await expect(page.locator(".tool-nav a.active")).toHaveAttribute(
    "href",
    `/${tools.at(-1)![0]}/`,
  );
  await navigate(page, "compress-pdf");
  await page
    .locator("#pdf-file")
    .setInputFiles("tests/fixtures/m5/normal-a4.pdf");
  await expect(page.locator(".compress-task")).toBeVisible();
  await expect(
    page.locator(".sign-task, .split-task, .organize-task"),
  ).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("browser back and forward restore clean tool pickers without stale overlays", async ({
  page,
}) => {
  // Local PDF tools share a document. Word and PowerPoint intentionally use
  // separate conversion pages; both cross-document histories are tested below.
  await page.goto("/");
  await page.locator("html").evaluate((element) => {
    element.setAttribute("data-audit-document", "history-navigation");
  });
  for (const [path] of localTools) {
    console.log("SYNTHETIC_HISTORY", "select", path);
    await selectToolPath(page, path);
    await expect(page).toHaveURL(new RegExp(`/${path}/$`));
  }
  for (const [path, id] of localTools.slice(0, -1).reverse()) {
    console.log("SYNTHETIC_HISTORY", "back-commit", path);
    // This is same-document SPA history. Assert the route and real picker below
    // instead of waiting for an unrelated document-wide load event in WebKit.
    await page.goBack({ waitUntil: "commit" });
    console.log("SYNTHETIC_HISTORY", "back-picker", path);
    await expect(page).toHaveURL(new RegExp(`/${path}/$`));
    await expect(page.locator("html")).toHaveAttribute(
      "data-audit-document",
      "history-navigation",
    );
    await checkPicker(page, id);
    console.log("SYNTHETIC_HISTORY", "back-complete", path);
  }
  for (const [path, id] of localTools.slice(1)) {
    console.log("SYNTHETIC_HISTORY", "forward-commit", path);
    await page.goForward({ waitUntil: "commit" });
    console.log("SYNTHETIC_HISTORY", "forward-picker", path);
    await expect(page).toHaveURL(new RegExp(`/${path}/$`));
    await expect(page.locator("html")).toHaveAttribute(
      "data-audit-document",
      "history-navigation",
    );
    await checkPicker(page, id);
    console.log("SYNTHETIC_HISTORY", "forward-complete", path);
  }
});

for (const [cloudPath, cloudPicker] of cloudTools) {
  test(`${cloudPath}: cloud page and local tools restore working pickers across document history`, async ({
    page,
  }) => {
    await page.goto("/merge-pdf/");
    await navigate(page, cloudPath);
    await expect(page).toHaveURL(new RegExp(`/${cloudPath}/$`));
    await checkPicker(page, cloudPicker);
    await navigate(page, "unlock-pdf");
    await checkPicker(page, "pdf-file");
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`/${cloudPath}/$`));
    await checkPicker(page, cloudPicker);
    await page.goForward();
    await expect(page).toHaveURL(/\/unlock-pdf\/$/);
    await checkPicker(page, "pdf-file");
  });
}

test("back from a completed task returns home and forward opens a fresh picker without reloading", async ({
  page,
}) => {
  await page.goto("/");
  await page.locator("html").evaluate((element) => {
    element.setAttribute("data-audit-document", "completed-navigation");
  });
  await navigate(page, "images-to-pdf");
  await page
    .locator("#photo-files")
    .setInputFiles("docs/ux/public-synthetic-only/image-a.png");
  await page
    .getByRole("button", { name: "Convert to PDF →", exact: true })
    .click();
  await expect(page.locator(".delivery")).toBeVisible();
  await page.goBack();
  await expect(page.locator(".tool-home")).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute(
    "data-audit-document",
    "completed-navigation",
  );
  await page.goForward();
  await expect(page).toHaveURL(/\/images-to-pdf\/$/);
  await checkPicker(page, "photo-files");
  await expect(page.locator(".delivery, .photo-list>li")).toHaveCount(0);
  await expect(page.locator("html")).toHaveAttribute(
    "data-audit-document",
    "completed-navigation",
  );
});

for (const destination of ["/split-pdf/", "/"]) {
  test(`history rate limit safely navigates to ${destination}`, async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("/images-to-pdf/");
    await expect(page.locator("#photo-files")).toBeVisible();
    await page.evaluate(() => {
      window.history.pushState = () => {
        throw new DOMException("Synthetic history rate limit", "SecurityError");
      };
    });
    if (destination === "/")
      await page.getByText("← All tools", { exact: true }).click();
    else await selectToolPath(page, "split-pdf");
    await expect(page).toHaveURL(new RegExp(`${destination}$`));
    if (destination === "/")
      await expect(page.locator(".tool-home")).toBeVisible();
    else await checkPicker(page, "pdf-file");
    expect(errors).toEqual([]);
  });
}
