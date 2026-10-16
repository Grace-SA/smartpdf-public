import {
  PDFDocument,
  PDFName,
  PDFDict,
  PDFArray,
  PDFRef,
  PDFObject,
  PDFRawStream,
  PDFNumber,
  degrees,
} from "pdf-lib";
import { inspectPdf, type CombineInspection } from "../combine/generate";
import { inspectNavigation } from "../combine/navigation";
import { LIMITS, validateSize } from "../core/contracts";
import { normalizeOptionalTagIndexes } from "../core/optional-tag-indexes";
import { trimDeletedAssociations } from "./deletion";
import { compactStreamStorage } from "./stream-storage";
import type { PageEntry } from "./model";
export const organizeErrors = {
  invalid:
    "Choose at least one page, without duplicates, and rotate in 90-degree steps.",
  unsupported:
    "This PDF cannot be organized while preserving its supported structure. Your previous document is unchanged.",
  referenced:
    "A retained link, bookmark, tag, form or document setting still refers to a deleted page. Keep that page or cancel these changes; no structure has been silently removed.",
  output:
    "The organized PDF did not pass validation. Your previous document is unchanged.",
} as const;

export async function inspectOrganize(
  bytes: Uint8Array,
): Promise<CombineInspection> {
  const check = await inspectPdf(bytes);
  if (!check.ok) return check;
  const doc = await PDFDocument.load(bytes, {
    updateMetadata: false,
    throwOnInvalidObject: true,
  });
  const preferences = doc.catalog.lookupMaybe(
    PDFName.of("ViewerPreferences"),
    PDFDict,
  );
  if (
    preferences?.has(PDFName.of("PrintPageRange")) ||
    doc.catalog.has(PDFName.of("Threads"))
  )
    return {
      ok: false,
      code: "UNSUPPORTED_PDF",
      reason: "navigation",
      detail:
        "This PDF has print-page ranges or article threads that page changes cannot yet preserve.",
    };
  return check;
}

export async function organizePdf(
  bytes: Uint8Array,
  plan: PageEntry[],
  adjustDeletedAssociations = false,
) {
  const prepared = await prepareOrganize(bytes);
  return prepared.create(plan, adjustDeletedAssociations);
}

/** One immutable, checked source per task. Each output still gets its own
 * document tree and full validation; no caller can supply an unchecked token. */
export async function prepareOrganize(input: Uint8Array) {
  validateSize(input.byteLength);
  const bytes = new Uint8Array(input);
  const check = await inspectOrganize(bytes);
  if (!check.ok) throw new Error(organizeErrors.unsupported);
  const pages = check.pages;
  return {
    pages,
    create: (plan: PageEntry[], adjust = false) =>
      organizeChecked(
        bytes,
        pages,
        plan.map((p) => ({ ...p })),
        adjust,
      ),
  };
}

async function organizeChecked(
  bytes: Uint8Array,
  pageCount: number,
  plan: PageEntry[],
  adjustDeletedAssociations: boolean,
) {
  if (
    !plan.length ||
    plan.length > pageCount ||
    new Set(plan.map((p) => p.id)).size !== plan.length ||
    new Set(plan.map((p) => p.source)).size !== plan.length ||
    plan.some(
      (p) =>
        !p.id ||
        !Number.isInteger(p.source) ||
        p.source < 0 ||
        p.source >= pageCount ||
        !Number.isInteger(p.turns) ||
        p.turns < 0 ||
        p.turns > 3,
    )
  )
    throw new Error(organizeErrors.invalid);
  const doc = await PDFDocument.load(bytes, {
    updateMetadata: false,
    throwOnInvalidObject: true,
  });
  const pages = doc.getPages();
  normalizeOptionalTagIndexes(doc);
  const navigation = inspectNavigation(doc);
  const kept = new Set(plan.map((p) => p.source));
  const deleted = new Set(
    pages.filter((_, i) => !kept.has(i)).map((p) => p.node),
  );
  if (deleted.size && adjustDeletedAssociations)
    trimDeletedAssociations(doc, kept);
  const rotations = pages.map((p) => p.getRotation().angle);
  // Materialize inherited values before changing the page tree. Retain original
  // object identities so destinations, annotations and tag references stay valid.
  for (const p of pages)
    for (const name of ["Resources", "MediaBox", "CropBox", "Rotate"]) {
      const key = PDFName.of(name),
        value = p.node.getInheritableAttribute(key);
      if (value) p.node.set(key, value);
    }
  for (let i = pages.length - 1; i >= 0; i--) doc.removePage(i);
  for (const entry of plan) {
    const p = pages[entry.source]!;
    p.setRotation(
      degrees(
        (((rotations[entry.source]! + entry.turns * 90) % 360) + 360) % 360,
      ),
    );
    doc.addPage(p);
  }
  if (navigation.hasLabels) {
    const nums: (number | PDFDict)[] = [];
    plan.forEach((entry, i) => {
      const [start, source] = navigation.labels
        .filter(([n]) => n <= entry.source)
        .at(-1)!;
      const label = source.clone();
      if (label.has(PDFName.of("S"))) {
        const n =
          source.lookupMaybe(PDFName.of("St"), PDFNumber)?.asNumber() ?? 1;
        label.set(PDFName.of("St"), PDFNumber.of(n + entry.source - start));
      }
      nums.push(i, label);
    });
    doc.catalog.set(PDFName.of("PageLabels"), doc.context.obj({ Nums: nums }));
  }
  const seen = new Set<PDFObject>(),
    refs = new Set<PDFRef>();
  let nodes = 0;
  function visit(raw: PDFObject, depth = 0): void {
    if (raw instanceof PDFRef) refs.add(raw);
    const object = doc.context.lookup(raw);
    if (!object) throw new Error(organizeErrors.unsupported);
    if (deleted.has(object as (typeof pages)[number]["node"]))
      throw new Error(organizeErrors.referenced);
    if (seen.has(object)) return;
    if (++nodes > LIMITS.nodes || depth > LIMITS.depth)
      throw new Error(organizeErrors.unsupported);
    seen.add(object);
    if (object instanceof PDFArray)
      for (const v of object.asArray()) visit(v, depth + 1);
    const dict =
      object instanceof PDFRawStream
        ? object.dict
        : object instanceof PDFDict
          ? object
          : undefined;
    if (dict) for (const [, v] of dict.entries()) visit(v, depth + 1);
  }
  if (doc.context.trailerInfo.Root) visit(doc.context.trailerInfo.Root);
  if (doc.context.trailerInfo.Info) visit(doc.context.trailerInfo.Info);
  // A fresh save must not serialize detached deleted pages and their private
  // streams merely because pdf-lib retains them in its indirect-object table.
  for (const [ref] of doc.context.enumerateIndirectObjects())
    if (!refs.has(ref)) doc.context.delete(ref);
  compactStreamStorage(doc);
  const result = await doc.save();
  const verified = await inspectPdf(result);
  if (!verified.ok || verified.pages !== plan.length)
    throw new Error(organizeErrors.output);
  return result;
}
