import type { WordCheck } from "./preflight-core";
export type WordOptions = {
  revisionView: "unchanged" | "final" | "original";
  omitComments: boolean;
};
export const defaultWordOptions = (): WordOptions => ({
  revisionView: "unchanged",
  omitComments: false,
});
export function blockingWordIssues(
  check: WordCheck | undefined,
  options: WordOptions,
) {
  const issues =
    check?.issues.filter(
      (issue) =>
        !(
          issue.code === "TRACKED_CHANGES" &&
          options.revisionView !== "unchanged"
        ) && !(issue.code === "COMMENTS" && options.omitComments),
    ) || [];
  if (check?.originalViewUnsupported && options.revisionView === "original")
    issues.push({
      code: "ORIGINAL_VIEW_UNSUPPORTED",
      message:
        "Use Word to restore this document’s original formatting or structure. Choose current content instead.",
    });
  return issues;
}
