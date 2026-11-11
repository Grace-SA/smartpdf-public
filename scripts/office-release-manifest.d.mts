export const officeRuntimePaths: string[];
export function prepareOfficeRuntime(
  source: string,
  folder: string,
): {
  word: ReturnType<
    typeof import("./word-release-manifest.mjs").prepareWordRuntime
  >;
  ppt: Record<string, unknown>;
  pdfword: Record<string, unknown>;
  files: { path: string; bytes: number; sha256: string }[];
  archive: { path: string; bytes: number; sha256: string };
  install: string;
  sharedAdmission: boolean;
  deployed: boolean;
};
