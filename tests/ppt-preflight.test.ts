import { execFileSync } from "node:child_process";
import { expect, it } from "vitest";

it("checks slide scope, relationships, active content, geometry and resource boundaries", () => {
  expect(() =>
    execFileSync(
      process.platform === "win32" ? "python" : "python3",
      ["-B", "server/ppt/test_preflight.py"],
      { encoding: "utf8" },
    ),
  ).not.toThrow();
});
