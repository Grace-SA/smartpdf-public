import { PDFDocument, StandardFonts, rgb } from "pdf-lib";
import { mkdir, writeFile } from "node:fs/promises";
await mkdir("docs/ux/public-synthetic-only", { recursive: true });
for (const [name, count] of [
  ["demo-a", 6],
  ["demo-b", 3],
]) {
  const pdf = await PDFDocument.create();
  pdf.setTitle("Public UX test - generated synthetic content");
  pdf.setAuthor("Synthetic test generator");
  const font = await pdf.embedFont(StandardFonts.Helvetica);
  for (let i = 1; i <= count; i++) {
    const p = pdf.addPage([300, 400]);
    p.drawRectangle({
      x: 0,
      y: 0,
      width: 300,
      height: 400,
      color: rgb(0.93, 0.95, 0.98),
    });
    p.drawText(`${name} / PAGE ${i}`, { x: 24, y: 320, size: 24, font });
    p.drawText("SYNTHETIC - NO PERSONAL DATA", {
      x: 24,
      y: 260,
      size: 12,
      font,
    });
    p.drawRectangle({
      x: 24,
      y: 70,
      width: 40 * i,
      height: 100,
      color: rgb(0.2, 0.3 + i / 20, 0.6),
    });
  }
  await writeFile(
    `docs/ux/public-synthetic-only/${name}.pdf`,
    await pdf.save(),
  );
}
