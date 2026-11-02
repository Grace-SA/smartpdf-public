import { execFileSync } from "node:child_process";
import { expect, it } from "vitest";
it("checks DOCX structure, active content, links and expansion budgets", () => {
  const result = execFileSync(
    process.env.PYTHON || (process.platform === "win32" ? "python" : "python3"),
    ["-B", "server/word/test_preflight.py"],
    { encoding: "utf8", stdio: "pipe" },
  );
  expect(result).toBe("");
});
