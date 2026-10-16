import {
  PDFDocument,
  PDFDict,
  PDFArray,
  PDFName,
  PDFObject,
  PDFRef,
} from "pdf-lib";
export class StructureFailure extends Error {
  constructor(
    public reason: "layers" | "tagged" | "attachments",
    detail: string,
  ) {
    super(detail);
  }
}
export const key = PDFName.of;
export function reader(
  doc: PDFDocument,
  reason: "layers" | "tagged" | "attachments",
) {
  const fail = (detail: string): never => {
    throw new StructureFailure(reason, detail);
  };
  const resolve = (v: PDFObject | undefined): PDFObject | undefined =>
    v instanceof PDFRef ? doc.context.lookup(v) : v;
  const dict = (v: PDFObject | undefined): PDFDict => {
    const d = resolve(v);
    return d instanceof PDFDict
      ? d
      : fail(`This PDF has incomplete ${reason} structures.`);
  };
  const array = (v: PDFObject | undefined): PDFObject[] => {
    const a = resolve(v);
    return a instanceof PDFArray
      ? a.asArray()
      : fail(`This PDF has incomplete ${reason} arrays.`);
  };
  const name = (v: PDFObject | undefined): string => {
    const n = resolve(v);
    return n instanceof PDFName ? n.decodeText() : "";
  };
  const keys = (d: PDFDict, allowed: string[]) => {
    for (const [k] of d.entries())
      if (!allowed.includes(k.decodeText()))
        fail(
          `This PDF uses an unsupported ${reason} feature (${k.decodeText()}). It cannot be preserved yet.`,
        );
  };
  return { fail, resolve, dict, array, name, keys };
}
