import path from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath, pathToFileURL } from "node:url";
import { readFile } from "node:fs/promises";
import { createWordService, runStirling } from "../word/service.mjs";
import { checkDocx } from "./docx-check.mjs";

const runner = fileURLToPath(
  new URL(
    process.env.PDFWORD_LOCAL_V2 === "1" ? "./local_runner.py" : "./runner.py",
    import.meta.url,
  ),
);
export function createPdfWordService(options = {}) {
  return createWordService({
    ...options,
    format: "pdfword",
    capabilities: {
      reconstruction: process.env.PDFWORD_LOCAL_V2 === "1",
      ocr:
        process.env.PDFWORD_LOCAL_V2 === "1" &&
        Boolean(
          process.env.PDFWORD_OCR_PYTHON && process.env.PDFWORD_MODEL_ROOT,
        ),
    },
    root:
      options.root ||
      process.env.PDFWORD_DATA_DIR ||
      path.join(tmpdir(), "smartpdf-pdfword-tasks"),
    origin:
      options.origin ||
      process.env.PDFWORD_PUBLIC_ORIGIN ||
      "http://127.0.0.1:4280",
    execute:
      options.execute || ((job, update) => runStirling(job, update, runner)),
    validate:
      options.validate ||
      (async (file) => {
        const actual = await checkDocx(file);
        const expected = JSON.parse(
          await readFile(
            path.join(path.dirname(file), "expected.json"),
            "utf8",
          ),
        );
        if (
          !Number.isInteger(expected.pages) ||
          expected.pages < 1 ||
          expected.pages > 200
        )
          throw Error("Invalid source page count");
        if (
          expected.schema === 2 &&
          (actual.sourceMarkers !== expected.pages ||
            actual.images !== expected.images ||
            actual.tables !== expected.tables)
        )
          throw Error("Word content does not match the conversion manifest");
        return { pages: expected.pages };
      }),
  });
}
if (
  process.argv[1] &&
  pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url
) {
  await runStirling({ directory: "--reap" }, () => {}, runner);
  const service = await createPdfWordService();
  service.server.listen(Number(process.env.PDFWORD_PORT || 4283), "127.0.0.1");
  for (const signal of ["SIGINT", "SIGTERM"])
    process.once(signal, () => void service.close());
}
