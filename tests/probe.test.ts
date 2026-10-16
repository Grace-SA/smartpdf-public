import { describe, it, expect } from "vitest";
import { probePdf } from "../src/core/probe";
import { LIMITS, validateSize } from "../src/core/contracts";
import { makeFixture, cases, type FixtureKind } from "./fixtures";
import { readFile } from "node:fs/promises";

describe.each([false, true])(
  "Structural probes, object streams=%s",
  (objectStreams) => {
    for (const [kind, reason] of Object.entries(cases)) {
      it(`rejects ${kind}`, async () => {
        const bytes = await makeFixture(kind as FixtureKind, objectStreams);
        expect(await probePdf(bytes)).toMatchObject({
          ok: false,
          code: "UNSUPPORTED_PDF",
          reason,
        });
      });
    }
    for (const kind of [
      "plain",
      "empty-annots",
      "metadata",
      "geometry",
      "token-text",
    ] as const) {
      it(`accepts ${kind} and leaves source untouched`, async () => {
        const bytes = await makeFixture(kind, objectStreams);
        const copy = bytes.slice();
        expect(await probePdf(bytes)).toMatchObject({ ok: true, pages: 2 });
        expect(bytes).toEqual(copy);
      });
    }
  },
);
it("rejects empty, disguised and truncated inputs", async () => {
  expect(await probePdf(new Uint8Array())).toMatchObject({ ok: false });
  expect(
    await probePdf(new TextEncoder().encode("<script>not pdf</script>")),
  ).toMatchObject({ ok: false });
  const bytes = await makeFixture();
  expect(await probePdf(bytes.slice(0, -20))).toMatchObject({ ok: false });
});
it("checks byte boundary without allocating large test files", () => {
  expect(() => validateSize(LIMITS.bytes)).not.toThrow();
  expect(() => validateSize(LIMITS.bytes + 1)).toThrow("RESOURCE_LIMIT");
});
it("checks exact page boundary and rejects one above", async () => {
  expect(await probePdf(await makeFixture("max-pages"))).toMatchObject({
    ok: true,
    pages: 200,
  });
  expect(await probePdf(await makeFixture("too-many-pages"))).toMatchObject({
    ok: false,
    reason: "pages",
  });
});
for (const [kind, reason] of [
  ["zero-pages", "pages"],
  ["huge-page", "geometry"],
  ["huge-image", "image"],
  ["broken-ref", "missingReference"],
  ["encrypted-marker", "encrypted"],
  ["deep", "complexity"],
] as const) {
  it(`safely rejects ${kind}`, async () =>
    expect(await probePdf(await makeFixture(kind))).toMatchObject({
      ok: false,
      reason,
    }));
}
for (const fixture of ["password-protected", "owner-encrypted"]) {
  it(`rejects genuine AES encryption: ${fixture}`, async () => {
    expect(
      await probePdf(
        new Uint8Array(await readFile(`tests/fixtures/${fixture}.pdf`)),
      ),
    ).toMatchObject({ ok: false, reason: "encrypted" });
  });
}
it("accepts independent raster-only synthetic scan", async () => {
  expect(
    await probePdf(new Uint8Array(await readFile("tests/fixtures/scan.pdf"))),
  ).toMatchObject({ ok: true, pages: 1 });
});
