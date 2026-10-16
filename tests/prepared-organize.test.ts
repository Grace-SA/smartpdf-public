import { it, expect } from "vitest";
import { PDFDocument } from "pdf-lib";
import { prepareOrganize } from "../src/organize/generate";

it("prepared splits snapshot their source and isolate each output tree", async () => {
  const doc = await PDFDocument.create();
  doc.addPage([300, 400]);
  doc.addPage([400, 500]);
  const bytes = await doc.save();
  const pending = prepareOrganize(bytes);
  bytes.fill(0);
  const prepared = await pending;
  const first = await prepared.create([{ id: "a", source: 0, turns: 1 }]);
  const second = await prepared.create([{ id: "b", source: 1, turns: 0 }]);
  const a = await PDFDocument.load(first),
    b = await PDFDocument.load(second);
  expect(a.getPage(0).getRotation().angle).toBe(90);
  expect(b.getPage(0).getRotation().angle).toBe(0);
  expect(b.getPage(0).getWidth()).toBe(400);
  await expect(
    prepared.create([{ id: "c", source: 2, turns: 0 }]),
  ).rejects.toThrow();
});
