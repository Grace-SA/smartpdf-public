export const wordRuntimePaths: string[];
export function prepareWordRuntime(source: string, folder: string): {
  image: string;
  fontProfile: string;
  fontFiles: number;
  archive: { path: string; bytes: number; sha256: string };
  files: { path: string; bytes: number; sha256: string }[];
  install: string;
  deployed: boolean;
};
