import { parentPort, workerData } from "node:worker_threads";
import { readFile } from "node:fs/promises";
import {
  PDFDocument,
  PDFName,
  PDFDict,
  PDFArray,
  PDFString,
  PDFHexString,
} from "pdf-lib";

try {
  const policy = typeof workerData === "object" ? workerData.policy : undefined;
  const bytes = await readFile(
    typeof workerData === "object" ? workerData.file : workerData,
  );
  if (bytes.length > 30 * 1024 ** 2) throw new Error("limit");
  const pdf = await PDFDocument.load(bytes, { updateMetadata: false });
  const pages = pdf.getPages();
  if (
    !pages.length ||
    pages.length > workerData.maxPages ||
    pages.some((p) => {
      const { width, height } = p.getSize();
      return (
        !Number.isFinite(width + height) ||
        width < 1 ||
        height < 1 ||
        width > 14400 ||
        height > 14400
      );
    })
  )
    throw new Error("limit");
  if (policy?.ppt) {
    if (pages.length !== policy.visible || pdf.isEncrypted)
      throw Error("scope");
    for (const page of pages) {
      const { width, height } = page.getSize();
      if (
        Math.abs(width - policy.width) > 0.1 ||
        Math.abs(height - policy.height) > 0.1
      )
        throw Error("geometry");
    }
    for (const [, object] of pdf.context.enumerateIndirectObjects()) {
      if (!(object instanceof PDFDict)) continue;
      for (const key of [
        "EmbeddedFiles",
        "EF",
        "AF",
        "JavaScript",
        "JS",
        "OpenAction",
        "AA",
        "RichMediaContent",
        "XFA",
        "AcroForm",
      ])
        if (object.has(PDFName.of(key))) throw Error("active content");
      const action = object.get(PDFName.of("S"));
      if (
        object.get(PDFName.of("Type"))?.toString() === "/Action" &&
        !["/URI", "/GoTo"].includes(action?.toString())
      )
        throw Error("action");
      const linkedAction = object.lookup(PDFName.of("A"));
      if (
        linkedAction &&
        (!(linkedAction instanceof PDFDict) ||
          !["/URI", "/GoTo"].includes(
            linkedAction.get(PDFName.of("S"))?.toString(),
          ) ||
          linkedAction.has(PDFName.of("Next")))
      )
        throw Error("action");
      if (action?.toString() === "/URI") {
        const uri = object.lookup(PDFName.of("URI"));
        if (
          !(uri instanceof PDFString || uri instanceof PDFHexString) ||
          !/^(https?:\/\/|mailto:)/i.test(uri.decodeText())
        )
          throw Error("link");
      }
      const annotations = object.lookup(PDFName.of("Annots"));
      if (annotations instanceof PDFArray)
        for (const ref of annotations.asArray()) {
          const annotation = pdf.context.lookup(ref);
          if (
            !(annotation instanceof PDFDict) ||
            annotation.get(PDFName.of("Subtype"))?.toString() !== "/Link"
          )
            throw Error("annotation");
        }
    }
  }
  parentPort.postMessage({ pages: pages.length });
} catch {
  parentPort.postMessage({ error: true });
}
