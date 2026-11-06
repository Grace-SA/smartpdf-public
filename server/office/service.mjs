import { createWordService, runStirling } from "../word/service.mjs";
import { createPptService } from "../ppt/service.mjs";
import { createOfficeAdmission } from "./admission.mjs";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

export async function createOfficeServices(options = {}) {
  let word;
  const admission = createOfficeAdmission({
    pauseWord: () => word.pauseStandby(),
    resumeWord: () => word.resumeStandby(),
  });
  word = await createWordService({
    ...options.word,
    admit: (_job, signal) => admission.acquire("word", signal),
    available: admission.available,
    onUnsafe: admission.fail,
  });
  let ppt;
  try {
    ppt = await createPptService({
      ...options.ppt,
      admit: (_job, signal) => admission.acquire("ppt", signal),
      available: admission.available,
      onUnsafe: admission.fail,
    });
  } catch (error) {
    admission.close();
    await word.close();
    throw error;
  }
  return {
    word,
    ppt,
    async close() {
      admission.close();
      await Promise.all([word.close(), ppt.close()]);
    },
  };
}

if (
  process.argv[1] &&
  pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url
) {
  await runStirling({ directory: "--reap" }, () => {});
  await runStirling(
    { directory: "--reap" },
    () => {},
    fileURLToPath(new URL("../ppt/runner.py", import.meta.url)),
  );
  const services = await createOfficeServices();
  try {
    for (const [service, port] of [
      [services.word, Number(process.env.WORD_PORT || 4268)],
      [services.ppt, Number(process.env.PPT_PORT || 4281)],
    ]) {
      await new Promise((resolve, reject) => {
        service.server.once("error", reject);
        service.server.listen(port, "127.0.0.1", () => {
          service.server.removeListener("error", reject);
          resolve();
        });
      });
    }
  } catch (error) {
    await services.close();
    throw error;
  }
  for (const signal of ["SIGINT", "SIGTERM"])
    process.once(signal, () => void services.close());
}
