import { test, expect } from "vitest";
import {
  PDFDocument,
  PDFName,
  PDFString,
  PDFRef,
  PDFNull,
  PDFDict,
} from "pdf-lib";
import { normalizeOptionalTagIndexes } from "../src/core/optional-tag-indexes";
import { organizePdf } from "../src/organize/generate";
const k = PDFName.of;
test("only reserved zero references for absent appearances are normalized", async () => {
  const d = await PDFDocument.create(),
    p = d.addPage();
  const zero = d.context.obj({ N: PDFRef.of(0, 0) }),
    missing = d.context.obj({ N: PDFRef.of(999, 0) });
  p.node.set(k("AP"), zero);
  p.node.set(k("AAPL:AKExtras"), d.context.obj({ AP: missing }));
  normalizeOptionalTagIndexes(d);
  expect(zero.get(k("N"), true)).toBe(PDFNull);
  expect(missing.get(k("N"))).toBe(PDFRef.of(999, 0));
});
test("backward-only bookmark nodes retain titles while removed-page destinations are disabled", async () => {
  const d = await PDFDocument.create(),
    p = d.addPage(),
    q = d.addPage();
  const root = d.context.obj({ Type: "Outlines" }),
    rootRef = d.context.register(root);
  const first = d.context.register(
    d.context.obj({
      Title: PDFString.of("First"),
      Parent: rootRef,
      Dest: [p.ref, "Fit"],
    }),
  );
  const last = d.context.register(
    d.context.obj({
      Title: PDFString.of("Backward-only"),
      Parent: rootRef,
      Prev: first,
      Dest: [q.ref, "Fit"],
    }),
  );
  root.set(k("First"), first);
  root.set(k("Last"), last);
  d.catalog.set(k("Outlines"), rootRef);
  const out = await PDFDocument.load(
    await organizePdf(await d.save(), [{ id: "p", source: 0, turns: 0 }], true),
  );
  const kept = out.catalog
    .lookup(k("Outlines"), PDFDict)
    .lookup(k("Last"), PDFDict);
  expect(kept.lookup(k("Title"), PDFString).decodeText()).toBe("Backward-only");
  expect(kept.has(k("Dest"))).toBe(false);
});
