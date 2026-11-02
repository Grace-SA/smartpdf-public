import { selectTool } from "./navigation";
import { expect, test } from "@playwright/test";
import { publicTools, toolPaths } from "../src/routes";

test("sitemap includes every public tool exactly once with working canonical pages", async ({
  request,
}) => {
  const response = await request.get("/sitemap.xml");
  expect(response.status()).toBe(200);
  const xml = await response.text();
  const locations = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map(
    (match) => match[1],
  );
  expect(new Set(locations).size).toBe(locations.length);
  expect(locations).toHaveLength(publicTools.length + 2);
  for (const path of [
    "/",
    ...publicTools.map((tool) => toolPaths[tool]),
    "/privacy/",
  ]) {
    const canonical = `https://smartpdf.com.au${path}`;
    expect(locations).toContain(canonical);
    const page = await request.get(path);
    expect(page.status()).toBe(200);
    expect(await page.text()).toContain(`rel="canonical" href="${canonical}"`);
  }
});

test("homepage exposes every crawlable tool and the wordmark", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.locator("header .brand-wordmark")).toHaveText("SmartPDF");
  await expect(page.locator('.tool-nav a[role="button"]')).toHaveCount(
    publicTools.length,
  );
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    "href",
    "https://smartpdf.com.au/",
  );
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Simple PDF tools",
  );
});

test("homepage stays ready and initializes only the selected PDF tool", async ({
  page,
}) => {
  let pdfResourcesRequested = false;
  page.on("request", (request) => {
    if (request.url().endsWith("/pdf-resources.json"))
      pdfResourcesRequested = true;
  });

  await page.goto("/");
  await page.waitForTimeout(1_200);
  await expect(page.getByText("Preparing local processing…")).toHaveCount(0);
  expect(pdfResourcesRequested).toBe(false);

  const tools: [string, string][] = [
    ["/merge-pdf/", "#combine-files"],
    ["/split-pdf/", "#pdf-file"],
    ["/organize-pdf/", "#pdf-file"],
    ["/images-to-pdf/", "#photo-files"],
    ["/sign-pdf/", "#pdf-file"],
    ["/compress-pdf/", "#pdf-file"],
    ["/rotate-pdf/", "#pdf-file"],
    ["/pdf-to-jpg/", "#pdf-file"],
    ["/watermark-pdf/", "#pdf-file"],
    ["/add-page-numbers/", "#pdf-file"],
  ];
  for (const [path, input] of tools) {
    await page.locator(`.tool-cards a[href="${path}"]`).click();
    await expect(page).toHaveURL(new RegExp(`${path.replaceAll("/", "\\/")}$`));
    await expect(page.locator(input)).toBeEnabled({ timeout: 30_000 });
    await page.getByRole("button", { name: "← All tools" }).click();
  }
  expect(pdfResourcesRequested).toBe(true);
});

test("direct tool URL has task-specific metadata and navigation", async ({
  page,
}) => {
  await page.goto("/compress-pdf/");
  await expect(page).toHaveTitle(/Compress PDF Online/);
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    "href",
    "https://smartpdf.com.au/compress-pdf/",
  );
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: "Compress PDF",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByText("Frequently asked questions")).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "More PDF tools" }),
  ).toBeVisible();
  await selectTool(page, "Split a PDF");
  await expect(page).toHaveURL(/\/split-pdf\/$/);
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: "Split PDF",
      exact: true,
    }),
  ).toBeVisible();
});

test("every indexable page includes free-focused SEO metadata", async ({
  page,
}) => {
  const paths = [
    "/",
    "/merge-pdf/",
    "/split-pdf/",
    "/organize-pdf/",
    "/images-to-pdf/",
    "/sign-pdf/",
    "/compress-pdf/",
    "/rotate-pdf/",
    "/pdf-to-jpg/",
    "/watermark-pdf/",
    "/add-page-numbers/",
  ];

  for (const path of paths) {
    await page.goto(path);
    await expect(page).toHaveTitle(/free/i);
    await expect(page.locator('meta[name="description"]')).toHaveAttribute(
      "content",
      /free/i,
    );
    await expect(page.locator('meta[name="keywords"]')).toHaveAttribute(
      "content",
      /free/i,
    );
  }
});
