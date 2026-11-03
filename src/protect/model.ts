export const PROTECT_ERROR = {
  CONNECTION:
    "Open this tool using HTTPS or localhost to protect a PDF securely.",
  INPUT:
    "This PDF cannot be protected safely. Use an ordinary, unencrypted PDF without signatures, Content Credentials or conformance declarations.",
  PASSWORD:
    "Use matching passwords of at least 8 characters and at most 127 UTF-8 bytes, without control characters.",
  RESOURCE: "This PDF exceeds the local processing limits. Try a smaller PDF.",
  ENGINE:
    "Password protection could not finish safely. Your original is unchanged. Re-enter your password to try again.",
  VERIFY:
    "The protected PDF could not be verified. Your original is unchanged.",
  CANCELLED: "Protection cancelled. Your original is unchanged.",
  TIMEOUT:
    "Protection took too long. Try a smaller PDF. Your original is unchanged.",
} as const;
export type ProtectCode = keyof typeof PROTECT_ERROR;
export class ProtectFailure extends Error {
  constructor(public readonly code: ProtectCode) {
    super(PROTECT_ERROR[code]);
  }
}

export function validPassword(password: string, confirmation = password) {
  return (
    password === confirmation &&
    !/[\uD800-\uDFFF]/u.test(password) &&
    Array.from(password).length >= 8 &&
    new TextEncoder().encode(password).length <= 127 &&
    !/[\p{Cc}\p{Cf}]/u.test(password) &&
    password.trim().length > 0
  );
}

export function protectionArgs(password: string) {
  if (!validPassword(password)) throw new ProtectFailure("PASSWORD");
  // Explicit option values prevent a password beginning with '--' being parsed
  // as an option. No shell or external process is involved.
  return [
    "--object-streams=disable",
    "/input.pdf",
    "--encrypt",
    `--user-password=${password}`,
    `--owner-password=${password}`,
    "--bits=256",
    "--",
    "/protected.pdf",
  ];
}
