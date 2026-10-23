export type UnlockReason =
  | "password"
  | "password-format"
  | "unsupported"
  | "invalid"
  | "resource"
  | "signature"
  | "standard"
  | "validation"
  | "engine"
  | "cancelled"
  | "timeout";
export type UnlockStatus = "password-required" | "accessible" | "not-encrypted";
export class UnlockFailure extends Error {
  constructor(public readonly reason: UnlockReason) {
    super(reason);
  }
}
export const unlockMessages: Record<UnlockReason, string> = {
  password: "That password didn't open this PDF. Try again.",
  "password-format":
    "This password contains unsupported characters or exceeds 127 UTF-8 bytes. It has not been changed.",
  unsupported:
    "This PDF uses a protection method or structure we don't support.",
  invalid: "This PDF is damaged or isn't a valid PDF. Choose another file.",
  resource:
    "This PDF exceeds the local processing limits. Try a smaller or less complex PDF.",
  signature:
    "This PDF has a digital signature or Content Credentials. Unlocking could invalidate them, so it was not changed.",
  standard:
    "This PDF declares a document standard. A new ordinary PDF requires your confirmation.",
  validation:
    "The unlocked copy could not be verified safely. Your original is unchanged.",
  engine:
    "Local processing couldn't finish. Your file is still here; please try again.",
  cancelled: "Processing cancelled. Your original is unchanged.",
  timeout: "Processing took too long. Try a smaller PDF or try again.",
};
export function validatePassword(password: string): void {
  const encoded = new TextEncoder().encode(password);
  if (
    encoded.length > 127 ||
    [...password].some(
      (c) => c.codePointAt(0)! < 32 || c.codePointAt(0) === 127,
    ) ||
    new TextDecoder().decode(encoded) !== password
  )
    throw new UnlockFailure("password-format");
}
export function classifyAccess(code: number, diagnostic: string): UnlockStatus {
  if (!diagnostic && code === 3) return "accessible";
  if (!diagnostic && code === 2) return "not-encrypted";
  if (/\/input\.pdf: invalid password\s*$/i.test(diagnostic))
    return "password-required";
  if (
    /(?:unsupported|unknown|unrecognized).*?(?:encryption|security)/i.test(
      diagnostic,
    )
  )
    throw new UnlockFailure("unsupported");
  throw new UnlockFailure("invalid");
}
