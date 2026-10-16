import { PDFDocument, PDFName, PDFNumber, PDFRawStream } from "pdf-lib";
import { readFile } from "node:fs/promises";
import { deflateSync } from "node:zlib";

export async function jpegResourceFixture(wrapped = false, understated = true) {
  const doc = await PDFDocument.create();
  const image = await doc.embedJpg(
    await readFile("tests/fixtures/review-30mp.jpg"),
  );
  doc.addPage().drawImage(image, { x: 0, y: 0, width: 300, height: 250 });
  await doc.flush();
  const stream = doc.context.lookup(image.ref) as PDFRawStream;
  if (understated) {
    stream.dict.set(PDFName.of("Width"), PDFNumber.of(1));
    stream.dict.set(PDFName.of("Height"), PDFNumber.of(1));
  }
  if (wrapped) {
    stream.dict.set(
      PDFName.of("Filter"),
      doc.context.obj(["FlateDecode", "DCTDecode"]),
    );
    doc.context.assign(
      image.ref,
      PDFRawStream.of(stream.dict, deflateSync(stream.contents)),
    );
  }
  return doc.save();
}
