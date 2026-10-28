import createQpdf from "@neslinesli93/qpdf-wasm";
import {
  PDFDocument,
  PDFName,
  PDFRawStream,
  PDFDict,
  decodePDFRawStream,
  pdfDocEncodingDecode,
} from "pdf-lib";
import { probePdf } from "../core/probe";
import { LIMITS, validateSize } from "../core/contracts";
import { prepareOrdinaryCopy } from "../core/ordinary-copy";
import { hasStandardDeclaration } from "../core/standard-metadata";
import { auditTrailer, canonicalGraph } from "./audit";
import {
  classifyAccess,
  UnlockFailure,
  validatePassword,
  type UnlockStatus,
} from "./model";

export type UnlockRequest =
  | { kind: "inspect"; bytes: ArrayBuffer }
  | { kind: "unlock"; bytes: ArrayBuffer; password: string; ordinary: boolean };
export type UnlockResult =
  { status: UnlockStatus } | { bytes: ArrayBuffer; pages: number };
const AUDIT_BYTES = 16 * 1024 * 1024;
export function legacyPasswordHex(password: string): string | null {
  if (![...password].some((c) => c.codePointAt(0)! > 127)) return null;
  const encoding = new Map(
    Array.from(
      { length: 256 },
      (_, i) => [pdfDocEncodingDecode(new Uint8Array([i])), i] as const,
    ),
  );
  if ([...password].some((c) => c === "\ufffd" || !encoding.has(c)))
    return null;
  return [...password]
    .map((c) => encoding.get(c)!.toString(16).padStart(2, "0"))
    .join("");
}
/** A fresh engine per operation: diagnostics and decrypted graphs never leave it. */
export async function processUnlock(
  request: UnlockRequest,
  wasmUrl: string,
  stage: (value: "unlock" | "verify") => void = () => {},
): Promise<UnlockResult> {
  const input = new Uint8Array(request.bytes);
  try {
    validateSize(input.length);
  } catch {
    throw new UnlockFailure(input.length === 0 ? "invalid" : "resource");
  }
  if (
    !/^%PDF-[12]\.\d/.test(new TextDecoder().decode(input.subarray(0, 8))) ||
    !/%%EOF\s*$/.test(
      new TextDecoder().decode(
        input.subarray(Math.max(0, input.length - 1024)),
      ),
    )
  )
    throw new UnlockFailure("invalid");
  let diagnostic = "",
    auditMode = false,
    overflow = false,
    auditCount = 0,
    auditBuffer: Uint8Array | undefined;
  const stderr = (byte: number) => {
    if (diagnostic.length < 32768) diagnostic += String.fromCharCode(byte);
  };
  const stdout = (byte: number) => {
    if (!auditMode) {
      stderr(byte);
      return;
    }
    if (auditCount >= AUDIT_BYTES) {
      overflow = true;
      throw new UnlockFailure("resource");
    }
    auditBuffer![auditCount++] = byte;
  };
  const engine = await createQpdf({
    locateFile: () => wasmUrl,
    noInitialRun: true,
    noFSInit: true,
    preRun: [
      (m: {
        FS: {
          init: (
            a: () => null,
            b: (n: number) => void,
            c: (n: number) => void,
          ) => void;
        };
      }) => m.FS.init(() => null, stdout, stderr),
    ],
  } as Parameters<typeof createQpdf>[0]);
  const fs = engine.FS as typeof engine.FS & {
    writeFile: (p: string, b: Uint8Array) => void;
    unlink: (p: string) => void;
  };
  const execute = (args: string[]) => {
    diagnostic = "";
    try {
      return engine.callMain(args);
    } catch {
      return -1;
    }
  };
  const failure = () => {
    if (overflow) throw new UnlockFailure("resource");
    if (/\/input\.pdf: invalid password\s*$/i.test(diagnostic))
      throw new UnlockFailure("password");
    if (
      /(?:unsupported|unknown|unrecognized).*?(?:encryption|security)/i.test(
        diagnostic,
      )
    )
      throw new UnlockFailure("unsupported");
    throw new UnlockFailure("invalid");
  };
  const audit = (file: string, args: string[] = []) => {
    auditBuffer = new Uint8Array(AUDIT_BYTES);
    auditCount = 0;
    auditMode = true;
    const code = execute([
      ...args,
      "--json-output",
      "--json-stream-data=inline",
      "--decode-level=none",
      file,
      "-",
    ]);
    auditMode = false;
    if (overflow) throw new UnlockFailure("resource");
    if (code !== 0 || diagnostic) throw new UnlockFailure("validation");
    let json: unknown;
    try {
      json = JSON.parse(
        new TextDecoder("utf-8", { fatal: true }).decode(
          auditBuffer.subarray(0, auditCount),
        ),
      );
    } catch {
      throw new UnlockFailure("validation");
    }
    auditBuffer = undefined;
    return json;
  };
  try {
    fs.writeFile("/input.pdf", input);
    const status = classifyAccess(
      execute(["--requires-password", "/input.pdf"]),
      diagnostic,
    );
    if (request.kind === "inspect") {
      if (status === "not-encrypted") {
        const checked = await probePdf(input, "preview");
        if (!checked.ok && checked.code !== "UNSUPPORTED_PDF")
          throw new UnlockFailure(
            checked.code === "RESOURCE_LIMIT" ? "resource" : "invalid",
          );
      }
      return { status };
    }
    if (status === "not-encrypted") return { status };
    validatePassword(request.password);
    let passwordArgs = ["--password=" + request.password];
    stage("unlock");
    const decrypt = () =>
      execute([
        ...passwordArgs,
        "--decrypt",
        "--stream-data=preserve",
        "/input.pdf",
        "/output.pdf",
      ]);
    let code = decrypt();
    if (code !== 0 && /\/input\.pdf: invalid password\s*$/i.test(diagnostic)) {
      const hex = legacyPasswordHex(request.password);
      if (hex !== null) {
        passwordArgs = ["--password-mode=hex-bytes", "--password=" + hex];
        code = decrypt();
      }
    }
    request.password = "";
    if (code !== 0 || diagnostic) failure();
    let output = fs.readFile("/output.pdf").slice();
    if (
      output.length > LIMITS.bytes ||
      input.length + output.length > 2 * LIMITS.bytes
    )
      throw new UnlockFailure("resource");
    stage("verify");
    const before = canonicalGraph(audit("/input.pdf", passwordArgs));
    passwordArgs = [];
    const after = audit("/output.pdf");
    if (auditTrailer(after)["/Encrypt"] || canonicalGraph(after) !== before)
      throw new UnlockFailure("validation");
    const checked = await probePdf(output, "preview");
    if (!checked.ok) {
      // The shared probe completes resource/geometry checks before returning its
      // collected unsupported structures. Only this isolated tool may preserve
      // these unedited objects, verified above as a complete logical graph.
      const allowed = new Set(["form", "annotations", "attachments"]);
      if (
        checked.code !== "UNSUPPORTED_PDF" ||
        !checked.reasons?.length ||
        !checked.reasons.every((r) => allowed.has(r))
      )
        throw new UnlockFailure(
          checked.reason === "signature"
            ? "signature"
            : checked.code === "RESOURCE_LIMIT"
              ? "resource"
              : checked.code === "INVALID_INPUT"
                ? "invalid"
                : "unsupported",
        );
    }
    const doc = await PDFDocument.load(output, {
      updateMetadata: false,
      throwOnInvalidObject: true,
    });
    if (doc.context.trailerInfo.Encrypt) throw new UnlockFailure("validation");
    let standard =
      checked.ok && !!checked.previewFeatures?.includes("standard");
    const info = doc.context.lookup(doc.context.trailerInfo.Info);
    if (
      info instanceof PDFDict &&
      ["GTS_PDFXVersion", "GTS_PDFXConformance", "GTS_PDFA1Version"].some(
        (key) => info.has(PDFName.of(key)),
      )
    )
      standard = true;
    for (const [, object] of doc.context.enumerateIndirectObjects())
      if (
        object instanceof PDFRawStream &&
        object.dict.get(PDFName.of("Type")) === PDFName.of("Metadata")
      ) {
        const metadata = decodePDFRawStream(object).getBytes(
          LIMITS.metadataBytes + 1,
        );
        if (metadata.length > LIMITS.metadataBytes)
          throw new UnlockFailure("resource");
        const xml = new TextDecoder().decode(metadata);
        if (/provenance|c2pa/i.test(xml)) throw new UnlockFailure("signature");
        if (hasStandardDeclaration(xml)) standard = true;
      }
    if (standard) {
      if (!request.ordinary) throw new UnlockFailure("standard");
      const ordinary = await prepareOrdinaryCopy(output, true);
      if (!ordinary) throw new UnlockFailure("validation");
      output = new Uint8Array(ordinary);
    }
    const pages = doc.getPageCount();
    if (pages < 1 || pages > LIMITS.pages) throw new UnlockFailure("resource");
    return { bytes: output.slice().buffer as ArrayBuffer, pages };
  } finally {
    if (request.kind === "unlock") request.password = "";
    diagnostic = "";
    auditBuffer = undefined;
    for (const file of ["/input.pdf", "/output.pdf"])
      try {
        fs.unlink(file);
      } catch {
        /* Aborted operations may not have created both files. */
      }
  }
}
