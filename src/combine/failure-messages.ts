// Only application-owned messages cross the worker boundary. Never forward
// parser exceptions that can contain document text or object contents.
const messages = [
  "These PDFs have different form defaults. Combine them separately to preserve their appearance and editing settings.",
  "These PDFs contain fields with the same name. Combine them separately to keep their values independent.",
  "These PDFs have different output colour settings. Combine files with the same colour profile separately to preserve their intended colours.",
  "A PDF without an output colour profile cannot be mixed with this profiled PDF without changing its colour settings.",
] as const;
export function failureMessageCode(error: unknown): number | undefined {
  if (!(error instanceof Error)) return;
  const code = messages.findIndex((message) => message === error.message);
  return code >= 0 ? code : undefined;
}
export function publicFailureMessage(code: unknown): string | undefined {
  return typeof code === "number" && Number.isInteger(code) && code >= 0
    ? messages[code]
    : undefined;
}
