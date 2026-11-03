import type { QpdfInstance } from "@neslinesli93/qpdf-wasm";
import { LIMITS } from "../core/contracts";
import { inspectProtect, structureDigest, verifyEncryption } from "./structure";
import { ProtectFailure, protectionArgs } from "./model";

/** Caller owns an isolated, one-use engine and must destroy its Worker. */
export async function generateProtected(
  source: Uint8Array,
  password: string,
  engine: QpdfInstance,
) {
  const args = protectionArgs(password);
  const fs = engine.FS as QpdfInstance["FS"] & {
    writeFile: (path: string, bytes: Uint8Array) => void;
    unlink: (path: string) => void;
  };
  const paths = ["/input.pdf", "/protected.pdf", "/verified.pdf"];
  try {
    const before = await inspectProtect(source);
    fs.writeFile(paths[0]!, source);
    if (engine.callMain(["--stream-data=preserve", ...args]) !== 0)
      throw new ProtectFailure("ENGINE");
    const candidate = fs.readFile(paths[1]!).slice();
    if (!candidate.length || candidate.length > LIMITS.bytes)
      throw new ProtectFailure("RESOURCE");
    await verifyEncryption(candidate);
    // qpdf does not emit encryption/key diagnostics. Fixed names only.
    if (
      engine.callMain([
        `--password=${password}`,
        "--decrypt",
        "--stream-data=preserve",
        paths[1]!,
        paths[2]!,
      ]) !== 0
    )
      throw new ProtectFailure("VERIFY");
    const reopened = fs.readFile(paths[2]!).slice();
    if (
      reopened.length > LIMITS.bytes ||
      (await structureDigest(reopened)) !== before.digest
    )
      throw new ProtectFailure("VERIFY");
    return { bytes: candidate, pages: before.pages };
  } finally {
    args.fill("");
    for (const path of paths) {
      try {
        fs.unlink(path);
      } catch {
        /* absent after failure */
      }
    }
  }
}
