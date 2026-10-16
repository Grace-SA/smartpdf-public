/* eslint-disable no-control-regex -- reject control bytes in untrusted URI references */
// URI actions are copied, never executed by the application. A relative address
// remains relative: do not guess a host or prepend https:// to user content.
export function passiveUriKind(
  value: string,
): "absolute" | "relative" | undefined {
  try {
    return ["https:", "http:", "mailto:"].includes(new URL(value).protocol)
      ? "absolute"
      : undefined;
  } catch {
    /* A relative reference is valid without being an absolute URL. */
  }
  if (!value || /[\x00-\x20\x7f\\]/.test(value) || value.startsWith("/"))
    return undefined;
  try {
    const decoded = decodeURIComponent(value);
    if (
      /[\x00-\x1f\x7f\\]/.test(decoded) ||
      decoded.startsWith("/") ||
      decoded.split(/[/?#]/)[0]!.includes(":")
    )
      return undefined;
  } catch {
    return undefined;
  }
  return "relative";
}
