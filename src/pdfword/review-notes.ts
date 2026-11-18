/** Presentation only: the service retains the complete diagnostic warnings. */
export function reviewNotes(warnings: readonly string[] = []) {
  let usedOcr = false;
  const details = new Set<string>();
  for (const warning of warnings) {
    if (
      /^Page \d+: text was recognized with OCR; check names and numbers\.$/.test(
        warning,
      )
    ) {
      usedOcr = true;
    } else if (
      !/^Page \d+: independently verified native text restored in \d+ OCR regions\.$/.test(
        warning,
      )
    ) {
      // Unknown warnings remain visible in details; never assume they are harmless.
      if (warning.trim()) details.add(warning);
    }
  }
  return { usedOcr, details: [...details] };
}
