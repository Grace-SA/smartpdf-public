// Synthetic 5 x 20-page / exactly 20 MiB total benchmark. Page-referenced comments
// exercise byte handling, not realistic image complexity; never user material.
import { PDFDocument, PDFName } from "pdf-lib";
import { mkdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
const folder = "tests/fixtures/combine";
await mkdir(folder, { recursive: true });
const manifest = [];
for (let i = 0; i < 5; i++) {
  const doc = await PDFDocument.create();
  let last;
  for (let n = 0; n < 20; n++) {
    const page = doc.addPage();
    page.drawText(`Benchmark ${i + 1} page ${n + 1}`, {
      x: 60,
      y: 100,
      size: 18,
    });
    const stream = doc.context.stream("%" + "x".repeat(209400) + "\n");
    const ref = doc.context.register(stream);
    page.node.addContentStream(ref);
    last = stream;
  }
  let bytes = await doc.save({ useObjectStreams: false });
  let padding = 209400;
  for (
    let attempt = 0;
    attempt < 10 && bytes.length !== 4 * 1024 * 1024;
    attempt++
  ) {
    padding += 4 * 1024 * 1024 - bytes.length;
    last!.contents = new TextEncoder().encode("%" + "x".repeat(padding) + "\n");
    last!.dict.delete(PDFName.of("Length"));
    bytes = await doc.save({ useObjectStreams: false });
  }
  if (bytes.length !== 4 * 1024 * 1024)
    throw Error(`Wrong size ${bytes.length}`);
  const path = `${folder}/benchmark-${i + 1}.pdf`;
  await writeFile(path, bytes);
  manifest.push({
    path,
    bytes: bytes.length,
    pages: 20,
    sha256: createHash("sha256").update(bytes).digest("hex"),
  });
}
await writeFile(
  `${folder}/benchmark-manifest.json`,
  JSON.stringify(
    {
      origin:
        "synthetic; page-referenced comment padding; not representative of image complexity",
      files: manifest,
    },
    null,
    2,
  ),
);
console.log("Generated five 20-page PDFs, exactly 20 MiB total.");
