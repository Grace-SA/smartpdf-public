import { describe, expect, it } from "vitest";
import { compressionArgs, summarizeCompression } from "../src/compress/model";

describe("M6 compression policy", () => {
  it("keeps highest quality structural and gives image modes explicit quality", () => {
    expect(compressionArgs("quality")).not.toContain("--optimize-images");
    expect(compressionArgs("recommended")).toContain("--jpeg-quality=80");
    expect(compressionArgs("smaller")).toContain("--jpeg-quality=65");
    for (const level of ["quality", "recommended", "smaller"] as const) {
      const args = compressionArgs(level);
      expect(args).toContain("--object-streams=generate");
      expect(args).toContain("--recompress-flate");
      expect(args).toContain("--compression-level=9");
    }
  });

  it("never reports or publishes a candidate larger than the source", () => {
    expect(summarizeCompression(1000, 1200, "recommended")).toEqual({
      originalBytes: 1000,
      outputBytes: 1000,
      savedPercent: 0,
      alreadyOptimized: true,
      level: "recommended",
    });
    expect(summarizeCompression(1000, 625, "smaller")).toEqual({
      originalBytes: 1000,
      outputBytes: 625,
      savedPercent: 37.5,
      alreadyOptimized: false,
      level: "smaller",
    });
  });
});
