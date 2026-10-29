import { describe, expect, it } from "vitest";
import { seoPages } from "../src/SeoContent";
import { toolFromPath, toolPaths } from "../src/routes";

describe("public tool routes and search metadata", () => {
  it("maps every canonical tool path in both directions", () => {
    for (const [tool, path] of Object.entries(toolPaths)) {
      expect(toolFromPath(path)).toBe(tool);
      expect(toolFromPath(path.slice(0, -1))).toBe(tool);
    }
    expect(toolFromPath("/unknown/")).toBeNull();
  });

  it("gives every tool unique descriptive metadata", () => {
    const pages = Object.values(seoPages);
    expect(new Set(pages.map((page) => page.title)).size).toBe(pages.length);
    expect(new Set(pages.map((page) => page.description)).size).toBe(
      pages.length,
    );
    for (const [tool, page] of Object.entries(seoPages)) {
      expect(page.title).toContain("Smart PDF");
      expect(page.description.length).toBeGreaterThan(80);
      expect(page.steps).toHaveLength(3);
      expect(page.faq).toHaveLength(
        tool === "protect"
          ? 4
          : tool === "numbers" || tool === "unlock"
            ? 3
            : 2,
      );
      if (tool === "unlock")
        expect(page.faq.map((item) => item[0])).toEqual([
          "Are my PDF and password uploaded?",
          "Can this recover a forgotten password?",
          "Will the new PDF ask for a password?",
        ]);
    }
  });
});
