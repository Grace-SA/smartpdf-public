import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";

test("FileReader buffers from another realm still reach the real PDF parser", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page.evaluate(() => {
    const peer = document.createElement("iframe");
    peer.hidden = true;
    document.body.append(peer);
    const foreign = peer.contentWindow as Window & typeof globalThis;
    const OriginalReader = FileReader;
    window.FileReader = class extends OriginalReader {
      get result(): string | ArrayBuffer | null {
        const value = super.result;
        if (value === null || typeof value === "string") return value;
        const buffer = new foreign.ArrayBuffer(value.byteLength);
        new foreign.Uint8Array(buffer).set(new Uint8Array(value));
        if (buffer instanceof ArrayBuffer)
          throw new Error("Expected a foreign buffer");
        return buffer;
      }
    };
  });
  await page.locator("#pdf-file").setInputFiles("tests/fixtures/plain.pdf");
  await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Page 2 of 2", { exact: true })).toBeVisible();
});

test("cancel during text reading keeps the previous preview and ignores late text", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const originalRead = ReadableStreamDefaultReader.prototype.read;
    ReadableStreamDefaultReader.prototype.read = async function () {
      const result = await originalRead.call(this);
      if (document.documentElement.dataset.holdText && result.value?.items) {
        document.documentElement.dataset.textPending = "1";
        await new Promise<void>((resolve) =>
          window.addEventListener("release-test-text", () => resolve(), {
            once: true,
          }),
        );
        document.documentElement.dataset.textReleased = "1";
      }
      return result;
    };
  });
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  await page.locator("#pdf-file").setInputFiles("tests/fixtures/plain.pdf");
  await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Page 2 of 2", { exact: true })).toBeVisible();
  await page.evaluate(() => {
    document.documentElement.dataset.holdText = "1";
  });
  await page.locator("#pdf-file").setInputFiles({
    name: "replacement.pdf",
    mimeType: "application/pdf",
    buffer: await readFile("tests/fixtures/plain.pdf"),
  });
  await expect(page.locator("html")).toHaveAttribute("data-text-pending", "1");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Cancelled");
  await page.evaluate(() => {
    delete document.documentElement.dataset.holdText;
    window.dispatchEvent(new Event("release-test-text"));
  });
  await expect(page.locator("html")).toHaveAttribute("data-text-released", "1");
  await expect(page.getByText("Page 2 of 2", { exact: true })).toBeVisible();
  await expect(page.locator("#pdf-file")).toBeEnabled();
});

test("plain PDF stays usable without newer binary and Promise APIs", async ({
  page,
  context,
  browserName,
}) => {
  await page.addInitScript(() => {
    Reflect.deleteProperty(Uint8Array.prototype, "toHex");
    Reflect.deleteProperty(Uint8Array, "fromBase64");
    Reflect.deleteProperty(Promise, "try");
    Reflect.deleteProperty(ReadableStream.prototype, Symbol.asyncIterator);
    const NativeBlob = Blob;
    // Remove the same APIs inside the real parser/rendering workers before
    // their code runs. No parser or successful result is mocked.
    window.Blob = class extends NativeBlob {
      constructor(parts?: BlobPart[], options?: BlobPropertyBag) {
        super(
          options?.type === "text/javascript"
            ? [
                'Reflect.deleteProperty(Uint8Array.prototype,"toHex");Reflect.deleteProperty(Uint8Array,"fromBase64");Reflect.deleteProperty(Promise,"try");\n',
                ...(parts ?? []),
              ]
            : parts,
          options,
        );
      }
    };
  });
  await page.goto("/");
  await expect(page.getByText("Ready for local processing")).toBeVisible();
  // Windows Playwright WebKit offline mode also breaks local Blob FileReader.
  // Block HTTP instead for this diagnostic engine; real devices test physical offline.
  if (browserName === "webkit")
    await context.route(/^https?:/, (route) => route.abort());
  else await context.setOffline(true);
  await page.locator("#pdf-file").setInputFiles("tests/fixtures/plain.pdf");
  await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
  await page.getByText("Text on this page", { exact: true }).click();
  await expect(page.locator(".page-text p")).not.toHaveText(
    "No text layer was found on this page.",
  );
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Page 2 of 2", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Clear session" }).click();
  await expect(page.locator("canvas")).toHaveCount(0);
});
