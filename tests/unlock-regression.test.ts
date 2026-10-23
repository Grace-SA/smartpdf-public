import { beforeAll, afterEach, test, expect } from "vitest";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { PDFDocument, PDFName } from "pdf-lib";
import { generateUnlockFixtures } from "../scripts/m12-fixtures.mjs";
import { processUnlock } from "../src/unlock/engine";
import { probePdf } from "../src/core/probe";
const wasm = pathToFileURL(
  process.cwd() + "/node_modules/@neslinesli93/qpdf-wasm/dist/qpdf.wasm",
).href;
const bytes = async (name: string) =>
  new Uint8Array(await readFile("tests/fixtures/m12/" + name + ".pdf")).buffer;
beforeAll(async () => {
  await mkdir(".test-output/unlock", { recursive: true });
  await generateUnlockFixtures();
}, 30000);
// Native CLI inspection codes are data, not Vitest's result status.
const priorExitCode = process.exitCode;
afterEach(() => {
  process.exitCode = priorExitCode;
});
for (const name of [
  "normal-a4",
  "mixed-page-size",
  "landscape",
  "100-pages",
  "200-pages",
  "scanned",
  "form",
  "chinese",
  "japanese",
  "image-heavy",
])
  test(`Unlock fixed encrypted variant preserves ${name}`, async () => {
    const result = await processUnlock(
      {
        kind: "unlock",
        bytes: await bytes("reg-" + name),
        password: "synthetic-user",
        ordinary: false,
      },
      wasm,
    );
    expect("bytes" in result).toBe(true);
    if (!("bytes" in result)) throw Error("Missing output");
    const source = await PDFDocument.load(
      await readFile(`tests/fixtures/m5/${name}.pdf`),
    );
    const out = await PDFDocument.load(result.bytes);
    await writeFile(
      `.test-output/unlock/reg-${name}.pdf`,
      new Uint8Array(result.bytes),
    );
    expect(out.context.trailerInfo.Encrypt).toBeUndefined();
    expect(result.pages).toBe(source.getPageCount());
    expect(out.getPages().map((p) => p.getSize())).toEqual(
      source.getPages().map((p) => p.getSize()),
    );
  });
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
  for (const role of ["user", "owner"])
    test(`Unlock authenticates known ${name} ${role} password`, async () => {
      const password =
        name === "unicode"
          ? role === "user"
            ? "合成 密碼✓"
            : "所有者 密碼✓"
          : name === "legacy-encoding"
            ? role === "user"
              ? "é space"
              : "Ö owner"
            : name === "special" && role === "user"
              ? "  \"quote'=合成✓  "
              : name === "empty-user" && role === "user"
                ? ""
                : "synthetic-" + role;
      const result = await processUnlock(
        {
          kind: "unlock",
          bytes: await bytes(name),
          password,
          ordinary: false,
        },
        wasm,
      );
      expect("bytes" in result).toBe(true);
      if ("bytes" in result)
        await writeFile(
          `.test-output/unlock/${name}-${role}.pdf`,
          new Uint8Array(result.bytes),
        );
    });
test("inspection distinguishes encrypted, empty-open-password and unencrypted", async () => {
  expect(
    await processUnlock(
      { kind: "inspect", bytes: await bytes("aes-256") },
      wasm,
    ),
  ).toEqual({ status: "password-required" });
  expect(
    await processUnlock(
      { kind: "inspect", bytes: await bytes("empty-user") },
      wasm,
    ),
  ).toEqual({ status: "accessible" });
  expect(
    await processUnlock(
      {
        kind: "inspect",
        bytes: new Uint8Array(await readFile("tests/fixtures/m5/normal-a4.pdf"))
          .buffer,
      },
      wasm,
    ),
  ).toEqual({ status: "not-encrypted" });
});
test("wrong credentials and unsupported handlers have separate safe failures", async () => {
  await expect(
    processUnlock(
      {
        kind: "unlock",
        bytes: await bytes("aes-256"),
        password: "incorrect-synthetic",
        ordinary: false,
      },
      wasm,
    ),
  ).rejects.toThrow("password");
  for (const name of ["handler", "revision"])
    await expect(
      processUnlock({ kind: "inspect", bytes: await bytes(name) }, wasm),
    ).rejects.toThrow("unsupported");
});
for (const name of ["navigation", "layers", "tags", "attachments"])
  test(`Unlock preserves ${name} through a verified graph`, async () => {
    const result = await processUnlock(
      {
        kind: "unlock",
        bytes: await bytes(name),
        password: "synthetic-owner",
        ordinary: false,
      },
      wasm,
    );
    expect("bytes" in result).toBe(true);
    if ("bytes" in result)
      await writeFile(
        `.test-output/unlock/${name}.pdf`,
        new Uint8Array(result.bytes),
      );
  });
for (const name of ["signature", "credentials"])
  test(`Unlock refuses ${name} without silently stripping protection evidence`, async () => {
    await expect(
      processUnlock(
        {
          kind: "unlock",
          bytes: await bytes(name),
          password: "synthetic-user",
          ordinary: false,
        },
        wasm,
      ),
    ).rejects.toThrow("signature");
  });
test("standard declarations require explicit ordinary-copy confirmation", async () => {
  await expect(
    processUnlock(
      {
        kind: "unlock",
        bytes: await bytes("standard"),
        password: "synthetic-user",
        ordinary: false,
      },
      wasm,
    ),
  ).rejects.toThrow("standard");
  const result = await processUnlock(
    {
      kind: "unlock",
      bytes: await bytes("standard"),
      password: "synthetic-user",
      ordinary: true,
    },
    wasm,
  );
  expect("bytes" in result).toBe(true);
  if ("bytes" in result) {
    await writeFile(
      ".test-output/unlock/standard.pdf",
      new Uint8Array(result.bytes),
    );
    const doc = await PDFDocument.load(result.bytes);
    const info = doc.context.lookup(doc.context.trailerInfo.Info);
    expect(info?.toString()).not.toContain(
      PDFName.of("GTS_PDFXVersion").toString(),
    );
  }
});
test("empty, corrupted, zero-page and over-limit inputs never produce a result", async () => {
  await expect(
    processUnlock({ kind: "inspect", bytes: new ArrayBuffer(0) }, wasm),
  ).rejects.toThrow("invalid");
  await expect(
    processUnlock(
      {
        kind: "inspect",
        bytes: new Uint8Array(await readFile("tests/fixtures/m5/corrupted.pdf"))
          .buffer,
      },
      wasm,
    ),
  ).rejects.toThrow("invalid");
  await expect(
    processUnlock(
      {
        kind: "unlock",
        bytes: await bytes("zero"),
        password: "synthetic-user",
        ordinary: false,
      },
      wasm,
    ),
  ).rejects.toThrow("invalid");
  for (const size of [50 * 1024 * 1024, 100 * 1024 * 1024])
    await expect(
      processUnlock({ kind: "inspect", bytes: new ArrayBuffer(size) }, wasm),
    ).rejects.toThrow("resource");
});
test("other tools continue rejecting encrypted inputs", async () => {
  expect(
    await probePdf(new Uint8Array(await bytes("aes-256")), "preview"),
  ).toMatchObject({ ok: false, reason: "encrypted" });
});
