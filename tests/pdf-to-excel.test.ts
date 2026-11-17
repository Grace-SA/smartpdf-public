import { describe, it, expect } from "vitest";
import {
  validatePdf,
  validPages,
  outputName,
  MAX_PDF_BYTES,
} from "../src/pdf-to-excel/model";
import { enabledTools, toolFromPath } from "../src/routes";
describe("PDF to Excel input rules", () => {
  it("accepts exact limit and case-insensitive extension", () =>
    expect(validatePdf({ name: "TABLE.PDF", size: MAX_PDF_BYTES })).toBe(""));
  it.each([
    { name: "x.pdf", size: 0 },
    { name: "x.pdf", size: MAX_PDF_BYTES + 1 },
    { name: "x.exe", size: 10 },
  ])("rejects invalid input %j", (f) => expect(validatePdf(f)).not.toBe(""));
  it.each(["", "all", "1", "1-3,5", "200", "1,1"])(
    "accepts page range %s",
    (r) => expect(validPages(r)).toBe(true),
  );
  it.each(["0", "201", "3-2", "1,", "-1", "NaN", "1.1", "1-99999999"])(
    "rejects page range %s",
    (r) => expect(validPages(r)).toBe(false),
  );
  it("makes a safe xlsx filename", () =>
    expect(outputName("../test.PDF")).toBe(".._test.xlsx"));
  it("keeps production discovery off until explicitly enabled", () => {
    expect(enabledTools(true, true)).not.toContain("pdfExcel");
    expect(enabledTools(true, true, true)).toContain("pdfExcel");
    expect(toolFromPath("/pdf-to-excel/", enabledTools())).toBeNull();
  });
});
