import { describe, expect, it } from "vitest";
import { reviewNotes } from "../src/pdfword/review-notes";

describe("conversion review notes", () => {
  it("collapses page OCR notices without dropping actual problems", () => {
    expect(
      reviewNotes([
        "Page 1: text was recognized with OCR; check names and numbers.",
        "Page 2: text was recognized with OCR; check names and numbers.",
        "Page 2: independently verified native text restored in 3 OCR regions.",
        "Page 2: table may be incomplete.",
        "Page 2: table may be incomplete.",
        "Page 3: table may be incomplete.",
      ]),
    ).toEqual({
      usedOcr: true,
      details: [
        "Page 2: table may be incomplete.",
        "Page 3: table may be incomplete.",
      ],
    });
  });
  it("keeps unknown and changed diagnostic messages", () => {
    expect(
      reviewNotes([
        "OCR failed",
        "Page 1: independently verified native text restored in 3 OCR regions. Check missing cells.",
      ]),
    ).toEqual({
      usedOcr: false,
      details: [
        "OCR failed",
        "Page 1: independently verified native text restored in 3 OCR regions. Check missing cells.",
      ],
    });
    expect(reviewNotes()).toEqual({ usedOcr: false, details: [] });
  });
});
