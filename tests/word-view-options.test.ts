import { it, expect } from "vitest";
import { inspectWordBytes } from "../src/word/preflight-core";
import {
  blockingWordIssues,
  defaultWordOptions,
} from "../src/word/view-options";
import { docxFixture } from "./docx-fixture";
it("requires both choices and never bypasses other input issues", () => {
  const value = inspectWordBytes(
    docxFixture(
      "<w:p><w:ins><w:r><w:t>New</w:t></w:r></w:ins><w:commentRangeStart/></w:p>",
      { "word/fonts/x.odttf": "synthetic" },
    ),
  );
  expect(blockingWordIssues(value, defaultWordOptions())).toHaveLength(3);
  expect(
    blockingWordIssues(value, {
      revisionView: "final",
      omitComments: true,
    }).map((x) => x.code),
  ).toEqual(["EMBEDDED_FONTS"]);
});
it("requires Word to restore unsupported original formatting history", () => {
  const value = inspectWordBytes(
    docxFixture(
      "<w:p><w:pPr><w:tblGridChange/></w:pPr><w:r><w:t>Text</w:t></w:r></w:p>",
    ),
  );
  expect(
    blockingWordIssues(value, {
      revisionView: "original",
      omitComments: false,
    }).map((x) => x.code),
  ).toContain("ORIGINAL_VIEW_UNSUPPORTED");
  expect(
    blockingWordIssues(value, { revisionView: "final", omitComments: false }),
  ).toEqual([]);
});

it("never resolves structural revision choices silently", () => {
  const check = inspectWordBytes(
    docxFixture(
      "<w:tbl><w:tr><w:trPr><w:ins/></w:trPr><w:tc><w:p><w:r><w:t>Row</w:t></w:r></w:p></w:tc></w:tr></w:tbl>",
    ),
  );
  for (const revisionView of ["final", "original"] as const)
    expect(
      blockingWordIssues(check, { revisionView, omitComments: true }).map(
        (x) => x.code,
      ),
    ).toContain("STRUCTURAL_REVISIONS");
});

it("allows only embedded-font substitution without bypassing hidden text", () => {
  const check = inspectWordBytes(
    docxFixture(
      "<w:p><w:r><w:rPr><w:vanish/></w:rPr><w:t>Text</w:t></w:r></w:p>",
      { "word/fonts/font.odttf": "synthetic" },
    ),
  );
  expect(
    blockingWordIssues(check, {
      revisionView: "unchanged",
      omitComments: false,
      useAvailableFonts: true,
    }).map((x) => x.code),
  ).toEqual(["HIDDEN_TEXT"]);
});
