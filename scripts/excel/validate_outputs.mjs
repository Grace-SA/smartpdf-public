// Real service output validation, separate from independent layout inspection.
import fs from "node:fs/promises";
import path from "node:path";
import { performance } from "node:perf_hooks";
import { checkPdf } from "../../server/word/service.mjs";

const root = path.resolve(process.argv[2]);
const cases = JSON.parse(
  (await fs.readFile(path.join(root, "cases.json"), "utf8")).replace(
    /^\uFEFF/,
    "",
  ),
);
const results = [];
for (const [index, item] of cases.entries()) {
  if (item.expectedReject) continue;
  const start = performance.now();
  try {
    const checked = await checkPdf(
      path.join(root, `output-${index}.pdf`),
      "excel",
    );
    results.push({
      case: index,
      ...checked,
      milliseconds: Math.round(performance.now() - start),
      passed: true,
    });
  } catch {
    results.push({ case: index, passed: false });
  }
}
await fs.writeFile(
  path.join(root, "service-validation.json"),
  JSON.stringify(results, null, 2),
);
console.log(
  JSON.stringify({
    outputs: results.length,
    passed: results.filter((r) => r.passed).length,
    failedCases: results.filter((r) => !r.passed).map((r) => r.case),
  }),
);
if (results.some((r) => !r.passed)) process.exitCode = 1;
