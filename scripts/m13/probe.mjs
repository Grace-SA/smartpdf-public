// Local research only: serve a fixed allowlist, never accept uploaded documents.
/* global console, process, document, window, URL */
import { createServer } from "node:http";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve, extname, sep } from "node:path";
import { createRequire } from "node:module";
const require = createRequire(
  resolve(process.env.M13_DEPENDENCY_PACKAGE || "package.json"),
);
const { chromium, webkit } = require("@playwright/test");
const root = resolve(".research/m13");
await mkdir(resolve(root, "outputs"), { recursive: true });
const mime = {
  ".html": "text/html",
  ".js": "application/javascript",
  ".wasm": "application/wasm",
  ".ttf": "font/ttf",
  ".json": "application/json",
};
const requests = [];
const server = createServer(async (req, res) => {
  res.setHeader("Cross-Origin-Opener-Policy", "same-origin");
  res.setHeader("Cross-Origin-Embedder-Policy", "require-corp");
  res.setHeader("Cache-Control", "no-store");
  try {
    const pathname = decodeURIComponent(
      new URL(req.url, "http://localhost").pathname,
    );
    if (pathname === "/memory-worker.js") {
      res.writeHead(200, { "Content-Type": "application/javascript" });
      const reduced =
        new URL(req.url, "http://localhost").searchParams.get("memory") ===
        "512";
      res.end(
        `const NativeMemory=WebAssembly.Memory; WebAssembly.Memory=class extends NativeMemory {constructor(options){${reduced ? "options={...options,initial:8192};" : ""}super(options);postMessage({type:'m13Memory',bytes:this.buffer.byteLength,initial:options.initial,maximum:options.maximum,shared:options.shared});}};importScripts('/matbee/package/dist/browser.worker.global.js');`,
      );
      return;
    }
    const target =
      pathname === "/"
        ? resolve("scripts/m13/probe.html")
        : pathname === "/font.ttf"
          ? resolve("vendor-fonts/NotoSansSC-variable.ttf")
          : resolve(root, "." + pathname);
    if (
      !target.startsWith(root + sep) &&
      target !== resolve("scripts/m13/probe.html") &&
      target !== resolve("vendor-fonts/NotoSansSC-variable.ttf")
    )
      throw Error("path");
    const data = await readFile(target);
    requests.push({ path: pathname, bytes: data.length });
    res.writeHead(200, {
      "Content-Type": mime[extname(target)] || "application/octet-stream",
    });
    res.end(data);
  } catch {
    res.writeHead(404);
    res.end();
  }
});
await new Promise((r) => server.listen(4243, "127.0.0.1", r));
if (process.argv.includes("--serve")) {
  console.log("Probe http://127.0.0.1:4243");
} else {
  const results = {
    environment: process.platform,
    engineVersion: "2.7.2",
    results: [],
    externalRequests: [],
    errors: [],
  };
  const manifest = JSON.parse(
    await readFile(resolve(root, "fixtures/manifest.json"), "utf8"),
  );
  try {
    for (const [browserName, browserType] of [
      ["chromium", chromium],
      ["webkit", webkit],
    ]) {
      let browser;
      try {
        browser = await browserType.launch({ headless: true });
        const context = await browser.newContext({
          acceptDownloads: true,
          viewport: { width: 1280, height: 900 },
        });
        await context.route("**/*", (route) => {
          const url = route.request().url();
          if (
            url.startsWith("http://127.0.0.1:4243/") ||
            url.startsWith("blob:") ||
            url.startsWith("data:")
          )
            return route.continue();
          results.externalRequests.push(url);
          return route.abort();
        });
        const page = await context.newPage();
        page.on("pageerror", (e) =>
          results.errors.push({ browserName, error: e.message }),
        );
        await page.goto("http://127.0.0.1:4243/");
        console.log(browserName, "initializing");
        await page.locator("#initialize").click();
        await page.waitForFunction(
          () =>
            /Ready|failed/.test(document.querySelector("#status").textContent),
          {},
          { timeout: 120000 },
        );
        const initialized = await page.locator("#status").innerText();
        results.results.push({
          browserName,
          phase: "init",
          status: initialized,
          metrics: await page.evaluate(() => window.research),
        });
        console.log(browserName, initialized);
        if (initialized === "Ready")
          for (const fixture of manifest) {
            const started = Date.now();
            await page
              .locator("#file")
              .setInputFiles(resolve(root, "fixtures", fixture.name + ".docx"));
            await page.waitForFunction(
              () =>
                /Complete|failed/.test(
                  document.querySelector("#status").textContent,
                ),
              {},
              { timeout: 60000 },
            );
            const status = await page.locator("#status").innerText();
            const item = {
              browserName,
              engine: "libreoffice",
              fixture: fixture.name,
              status,
              ms: Date.now() - started,
              metrics: await page.evaluate(() => window.research),
            };
            if (status === "Complete") {
              const downloadPromise = page.waitForEvent("download");
              await page.locator("#download").click();
              await (
                await downloadPromise
              ).saveAs(
                resolve(
                  root,
                  "outputs",
                  browserName + "-" + fixture.name + ".pdf",
                ),
              );
            }
            results.results.push(item);
            console.log(browserName, fixture.name, status, item.ms);
          }
        for (const name of ["empty", "corrupt"])
          if (initialized === "Ready") {
            await page
              .locator("#file")
              .setInputFiles(resolve(root, "fixtures", name + ".docx"));
            let status;
            try {
              await page.waitForFunction(
                () =>
                  /Complete|failed/.test(
                    document.querySelector("#status").textContent,
                  ),
                {},
                { timeout: 15000 },
              );
              status = await page.locator("#status").innerText();
            } catch {
              status = "Timed out after 15 seconds";
            }
            results.results.push({ browserName, fixture: name, status });
          }
        await context.close();
        const lightContext = await browser.newContext();
        const light = await lightContext.newPage();
        await light.goto("http://127.0.0.1:4243/");
        for (const engine of ["docx-preview", "mammoth"])
          for (const fixture of manifest) {
            await light.locator("#engine").selectOption(engine);
            await light
              .locator("#file")
              .setInputFiles(resolve(root, "fixtures", fixture.name + ".docx"));
            await light.waitForFunction(
              () =>
                /Complete|failed/.test(
                  document.querySelector("#status").textContent,
                ),
              {},
              { timeout: 30000 },
            );
            const metrics = await light.evaluate(() => window.research);
            const item = {
              browserName,
              engine,
              fixture: fixture.name,
              status: await light.locator("#status").innerText(),
              metrics,
            };
            results.results.push(item);
            if (
              engine === "docx-preview" &&
              fixture.name === "automatic-pagination"
            )
              await light.screenshot({
                path: resolve(
                  root,
                  "outputs",
                  browserName + "-docx-preview-flow.png",
                ),
                fullPage: false,
              });
            console.log(
              browserName,
              engine,
              fixture.name,
              item.status,
              metrics.pages?.length,
            );
          }
        await lightContext.close();
      } catch (e) {
        results.errors.push({ browserName, error: e.message });
        console.log(browserName, "ERROR", e.message);
      } finally {
        if (browser) await browser.close();
        await writeFile(
          resolve(root, "results.json"),
          JSON.stringify({ ...results, requests }, null, 2),
        );
      }
    }
  } finally {
    server.close();
  }
}
