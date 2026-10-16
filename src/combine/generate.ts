import {
  inspectNavigation,
  copyWithNavigation,
  finishNavigation,
  navigationFailure,
} from "./navigation";
import { PDFDocument, PDFName, PDFNumber, PDFDict, PDFPage } from "pdf-lib";
import { preserveOutputIntents } from "./output-intents";
import { preserveFlatForm } from "../core/flat-form";
import { inspectLayers, copyLayers, finishLayers } from "./layers";
import { StructureFailure } from "./structure";
import {
  inspectAttachments,
  copyAttachments,
  finishAttachments,
} from "./attachments";
import { inspectTags, copyTags, finishTags } from "./tags";
import { probePdf } from "../core/probe";
import { LIMITS, type ProbeResult } from "../core/contracts";
export const COMBINE_LIMITS = {
  count: 10,
  bytes: LIMITS.bytes,
  pages: LIMITS.pages,
};
export function validateInputs(inputs: Uint8Array[], minimum = 2) {
  if (inputs.length < minimum || inputs.length > COMBINE_LIMITS.count)
    throw new Error("Choose 2–10 PDFs to combine.");
  if (inputs.reduce((n, b) => n + b.byteLength, 0) > COMBINE_LIMITS.bytes)
    throw new Error("Use at most 30 MiB of PDF inputs in this task.");
}
export type CombineInspection = ProbeResult & { detail?: string };
export async function inspectPdf(
  bytes: Uint8Array,
  stage: (text: string) => void = () => {},
  options: { preserveAnnotationExtensions?: boolean } = {},
): Promise<CombineInspection> {
  const result = await probePdf(bytes, "combine", stage);
  if (!result.ok) return result;
  try {
    stage("Checking links and reading order…");
    const doc = await PDFDocument.load(bytes, {
      updateMetadata: false,
      throwOnInvalidObject: true,
    });
    const navigation = inspectNavigation(doc, options);
    inspectLayers(doc);
    const tags = inspectTags(doc);
    function checkBookmarks(items: typeof navigation.bookmarks) {
      for (const item of items) {
        const se = item.source.get(PDFName.of("SE"));
        if (se && !tags?.nodes.has(doc.context.lookup(se, PDFDict)))
          throw new Error("Missing bookmark structure target.");
        checkBookmarks(item.children);
      }
    }
    checkBookmarks(navigation.bookmarks);
    return result;
  } catch (error) {
    return {
      ok: false,
      code: "UNSUPPORTED_PDF",
      reason: error instanceof StructureFailure ? error.reason : "navigation",
      detail:
        error instanceof StructureFailure ? error.message : navigationFailure,
    };
  }
}
export async function combinePdfs(
  inputs: Uint8Array[],
  progress: (done: number) => void,
  stage: (text: string) => void = () => {},
) {
  validateInputs(inputs);
  let pages = 0;
  // Preflight the whole batch before producing any result.
  for (const bytes of inputs) {
    const result = await inspectPdf(bytes);
    if (!result.ok)
      throw new Error(
        "An input is not supported for combining. Remove it and try again.",
      );
    pages += result.pages;
    if (pages > COMBINE_LIMITS.pages)
      throw new Error("Use at most 200 pages in total.");
  }
  const output = await PDFDocument.create();
  const navigation: Awaited<ReturnType<typeof copyWithNavigation>>[] = [];
  const layers: ReturnType<typeof copyLayers>[] = [];
  const tags: ReturnType<typeof copyTags>[] = [];
  const attachments: ReturnType<typeof copyAttachments>[] = [];
  let nextTagKey = 0;
  const intentState: { identity?: string; unprofiledContent: boolean } = {
    unprofiledContent: false,
  };
  const orphanPages: PDFPage[] = [];
  const formState: { identity?: string; names: Set<string> } = {
    names: new Set(),
  };
  for (const [index, bytes] of inputs.entries()) {
    const source = await PDFDocument.load(bytes, {
      updateMetadata: false,
      throwOnInvalidObject: true,
    });
    const plan = inspectNavigation(source);
    const layerPlan = inspectLayers(source);
    const tagPlan = inspectTags(source);
    const attachmentPlan = inspectAttachments(source);
    const part = await copyWithNavigation(output, source, plan, index);
    preserveOutputIntents(output, source, part.copier, intentState);
    preserveFlatForm(output, source, part.copier, part.annotations, formState);
    navigation.push(part);
    attachments.push(
      copyAttachments(output, attachmentPlan, part.copier, index),
    );
    layers.push(copyLayers(layerPlan, part.copier));
    const tagPart = copyTags(
      output,
      tagPlan,
      part.copier,
      part.pages,
      index,
      nextTagKey,
      part.annotations,
    );
    tags.push(tagPart);
    for (const link of part.structureLinks) {
      const ref = tagPart?.refs.get(link.source);
      if (!ref) throw new Error("Missing bookmark structure target.");
      link.output.set(PDFName.of("SE"), ref);
    }
    const indexed = new Set(tagPlan?.parents.map((p) => p.page) ?? []);
    part.pages.forEach((p, i) => {
      if (p.node.has(PDFName.of("StructParents")) && !indexed.has(i))
        orphanPages.push(p);
    });
    if (tagPart) nextTagKey = tagPart.nextKey;
    progress(index + 1);
  }
  finishNavigation(output, navigation);
  finishAttachments(output, attachments);
  finishLayers(output, layers);
  finishTags(output, tags);
  for (const p of orphanPages)
    p.node.set(PDFName.of("StructParents"), PDFNumber.of(nextTagKey++));
  const tagRoot = output.catalog.lookupMaybe(
    PDFName.of("StructTreeRoot"),
    PDFDict,
  );
  if (tagRoot)
    tagRoot.set(PDFName.of("ParentTreeNextKey"), PDFNumber.of(nextTagKey));
  stage("Preparing the combined PDF…");
  const bytes = await output.save();
  stage("Checking the combined PDF…");
  const check = await inspectPdf(bytes, stage);
  if (!check.ok || check.pages !== pages)
    throw new Error(
      "The combined PDF did not pass validation. Try fewer or simpler PDFs.",
    );
  return bytes;
}
