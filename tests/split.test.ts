import { it, expect } from "vitest";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { PDFDocument } from "pdf-lib";
import { splitGroups, partNames } from "../src/split/model";
import { splitPdf } from "../src/split/generate";
import {
  emptySession,
  commitDocument,
  commitWorkspace,
  currentDocument,
  sessionBytes,
  type DocumentRevision,
} from "../src/session";
it("parses groups in source order and refuses duplicates, overlap and empty groups", () => {
  expect(splitGroups("1-3\n4-7\n8-10", 10).map((g) => g.length)).toEqual([
    3, 4, 3,
  ]);
  expect(splitGroups("5,1-3", 10)).toEqual([[0, 1, 2, 4]]);
  for (const text of ["0", "11", "5-2", "1,1", "1-3\n3-5", "1\n\n2", "1,", ""])
    expect(() => splitGroups(text, 10)).toThrow();
  expect(splitGroups("", 50, true)).toHaveLength(50);
  expect(() => splitGroups("", 51, true)).toThrow("50 results");
  expect(
    partNames("test.pdf", 2, ["test-part-01.pdf", "TEST-PART-01-2.pdf"]),
  ).toEqual(["test-part-01-3.pdf", "test-part-02.pdf"]);
});
it("splits all groups, preserves page geometry, refuses overlaps and enforces aggregate budget", async () => {
  const source = await PDFDocument.create();
  for (let i = 0; i < 10; i++)
    source.addPage([300 + i, 400 + i]).drawText(`Original ${i + 1}`);
  const bytes = await source.save();
  const outputs = await splitPdf(
    bytes,
    splitGroups("1-3\n4-7\n8-10", 10),
    false,
    1000000,
    () => {},
  );
  const docs = await Promise.all(outputs.map((b) => PDFDocument.load(b)));
  expect(docs.map((d) => d.getPageCount())).toEqual([3, 4, 3]);
  expect(docs.flatMap((d) => d.getPages().map((p) => p.getWidth()))).toEqual(
    Array.from({ length: 10 }, (_, i) => 300 + i),
  );
  await expect(
    splitPdf(bytes, [[0], [0]], false, 1000000, () => {}),
  ).rejects.toThrow("overlapping");
  await expect(
    splitPdf(bytes, [[0], [1]], false, 10, () => {}),
  ).rejects.toThrow("capacity");
  await mkdir("docs/private-samples/m4", { recursive: true });
  await writeFile("docs/private-samples/m4/source.pdf", bytes);
  for (const [i, b] of outputs.entries())
    await writeFile(`docs/private-samples/m4/part-${i + 1}.pdf`, b);
});
it("associated splitting is explicit and never silently removes cross-part references", async () => {
  const bytes = new Uint8Array(
    await readFile("tests/fixtures/organize/linked.pdf"),
  );
  const doc = await PDFDocument.load(bytes);
  const groups = Array.from({ length: doc.getPageCount() }, (_, i) => [i]);
  await expect(
    splitPdf(bytes, groups, false, 1000000, () => {}),
  ).rejects.toThrow();
  const outputs = await splitPdf(bytes, groups, true, 1000000, () => {});
  expect(outputs).toHaveLength(doc.getPageCount());
});
const revision = (id: string, name: string, size = 20): DocumentRevision => ({
  id,
  file: new File([new Uint8Array(size)], name),
  generated: true,
  label: "Edit",
  pageIds: [id],
});
it("task publication keeps only the source and current outputs, with no undo snapshots", () => {
  const a = revision("a", "source.pdf"),
    b = revision("b", "part.pdf"),
    c = revision("c", "replacement.pdf");
  let s = commitDocument(emptySession(), a);
  s = commitWorkspace(s, {
    documents: { a, b },
    activeId: "a",
    results: ["b"],
  });
  expect(currentDocument(s)).toBe(a);
  expect(sessionBytes(s)).toBe(40);
  s = commitWorkspace(s, {
    documents: { a, b, c },
    activeId: "a",
    results: ["c"],
  });
  expect(s.present.documents.b).toBeUndefined();
  expect(sessionBytes(s)).toBe(40);
  expect(Object.keys(s)).toEqual(["present"]);
});
it("a fresh input replaces the task without retaining previous results", () => {
  const a = revision("a", "old.pdf"),
    b = revision("b", "new.pdf");
  let s = commitWorkspace(emptySession(), {
    documents: { a },
    activeId: null,
    results: ["a"],
  });
  s = commitDocument(s, b);
  expect(s.present.results).toEqual([]);
  expect(Object.keys(s.present.documents)).toEqual(["b"]);
  expect(sessionBytes(s)).toBe(20);
});
it("task budget is unique-file based and refuses overflow atomically", () => {
  const a = revision("a", "source.pdf"),
    b = { ...a, id: "b" };
  const s = commitWorkspace(emptySession(), {
    documents: { a, b },
    activeId: "a",
    results: ["b"],
  });
  expect(sessionBytes(s)).toBe(20);
  const large = revision("large", "large.pdf", 60 * 1024 * 1024);
  expect(() =>
    commitWorkspace(s, {
      documents: { a, large },
      activeId: "a",
      results: ["large"],
    }),
  ).toThrow("budget");
  expect(s.present.results).toEqual(["b"]);
});
