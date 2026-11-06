export const requiredLocalChecks: string[];
export function verifyLocalRelease(options: {
  repository: string;
  commit: string;
  evidence: string;
}): {
  mode: string;
  releaseCommit: string;
  testedCommit: string;
  sourceTree: string;
  manifestSha256: string;
  authorization: unknown;
  runner: unknown;
  summaries: unknown[];
  manifest: string;
  files: { path: string; sha256: string; source: string }[];
};
export function copyLocalReleaseProof(
  proof: ReturnType<typeof verifyLocalRelease>,
  folder: string,
): Record<string, unknown>;
export function verifyGitHubRelease(
  repository: string,
  commit: string,
): Promise<{ mode: string; releaseCommit: string; checks: string }>;
