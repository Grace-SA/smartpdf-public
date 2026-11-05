import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { tmpdir } from "node:os";
import { readFile } from "node:fs/promises";
import { createWordService, runStirling, checkPdf } from "../word/service.mjs";

export function createPptService(options = {}) {
  return createWordService({
    ...options,
    format: "ppt",
    root:
      options.root ||
      process.env.PPT_DATA_DIR ||
      path.join(tmpdir(), "smartpdf-ppt-tasks"),
    origin:
      options.origin ||
      process.env.PPT_PUBLIC_ORIGIN ||
      "http://127.0.0.1:4280",
    execute:
      options.execute ||
      ((job, update) =>
        runStirling(
          job,
          update,
          fileURLToPath(new URL("./runner.py", import.meta.url)),
        )),
    validate:
      options.validate ||
      (async (file) =>
        checkPdf(file, {
          ppt: true,
          ...JSON.parse(
            await readFile(
              path.join(path.dirname(file), "expected.json"),
              "utf8",
            ),
          ),
        })),
  });
}

if (
  process.argv[1] &&
  pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url
) {
  await runStirling(
    { directory: "--reap" },
    () => {},
    fileURLToPath(new URL("./runner.py", import.meta.url)),
  );
  const service = await createPptService();
  service.server.listen(Number(process.env.PPT_PORT || 4281), "127.0.0.1", () =>
    console.log("PowerPoint conversion service ready on loopback."),
  );
  for (const signal of ["SIGINT", "SIGTERM"])
    process.once(signal, () => void service.close());
}
