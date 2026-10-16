import {
  PDFDocument,
  PDFName,
  PDFDict,
  PDFArray,
  PDFRef,
  PDFObject,
  PDFRawStream,
  PDFInvalidObject,
  PDFNumber,
  PDFString,
  PDFHexString,
  PDFNull,
  EncryptedPDFError,
  decodePDFRawStream,
} from "pdf-lib";
import { XMLValidator } from "fast-xml-parser";
import { hasStandardDeclaration } from "./standard-metadata";
import { inspectInlineImages } from "./inline-images";
import { checkJpegDimensions } from "./jpeg-dimensions";
import { passiveAnnotations } from "./annotations";
import { flatForm } from "./flat-form";
import { normalizeOptionalTagIndexes } from "./optional-tag-indexes";
import { checkFlateImage } from "./stream-image-check";
import { passiveUriKind } from "./passive-uri";
import { outputIntents } from "../combine/output-intents";
import { inspectAttachments } from "../combine/attachments";
import {
  LIMITS,
  ProbeFailure,
  failure,
  validateSize,
  type ProbeResult,
  type Reason,
} from "./contracts";

const forbiddenKeys: Record<string, Reason> = {
  AcroForm: "form",
  XFA: "form",
  FT: "form",
  ByteRange: "signature",
  DocMDP: "signature",
  Perms: "signature",
  EmbeddedFiles: "attachments",
  EF: "attachments",
  AF: "attachments",
  Collection: "attachments",
  JavaScript: "actions",
  JS: "actions",
  AA: "actions",
  OCProperties: "layers",
  OC: "layers",
  OCGs: "layers",
  Outlines: "navigation",
  PageLabels: "navigation",
  Dests: "navigation",
  Dest: "navigation",
  StructTreeRoot: "tagged",
  MarkInfo: "tagged",
  RichMediaContent: "multimedia",
  RichMediaSettings: "multimedia",
  Movie: "multimedia",
  Sound: "multimedia",
  GTS_PDFXVersion: "standard",
  GTS_PDFXConformance: "standard",
  OutputIntents: "standard",
};
const actionTypes = new Set([
  "JavaScript",
  "Launch",
  "URI",
  "GoTo",
  "GoToR",
  "GoToE",
  "Named",
  "SubmitForm",
  "ResetForm",
  "ImportData",
  "Rendition",
  "Movie",
  "Sound",
  "Hide",
  "SetOCGState",
  "Trans",
  "GoTo3DView",
]);
function reject(reason: Reason): never {
  throw new ProbeFailure("UNSUPPORTED_PDF", reason);
}
function name(value: PDFObject | undefined): string {
  return value instanceof PDFName ? value.decodeText() : "";
}

function inspectMetadata(
  stream: PDFRawStream,
  unsupported: (reason: Reason) => void,
): void {
  const decoded = decodePDFRawStream(stream).getBytes(LIMITS.metadataBytes + 1);
  if (decoded.length > LIMITS.metadataBytes)
    throw new ProbeFailure("RESOURCE_LIMIT", "complexity");
  // XMP packet processing instructions are an envelope, not XML content.
  // Some office exporters write a truncated UTF-8 BOM in xpacket's begin
  // value. Omit only that leading PI for inspection; preserve source bytes.
  let payload = decoded;
  if (new TextDecoder().decode(decoded.subarray(0, 9)) === "<?xpacket") {
    for (let i = 9; i < Math.min(decoded.length - 1, 1024); i++)
      if (decoded[i] === 63 && decoded[i + 1] === 62) {
        payload = decoded.subarray(i + 2);
        break;
      }
  }
  const xml = new TextDecoder("utf-8", { fatal: true }).decode(payload);
  // Metadata is parsed separately; no document bytes are searched for PDF tokens.
  if (/<!DOCTYPE|<!ENTITY/i.test(xml) || XMLValidator.validate(xml) !== true)
    reject("malformed");
  if (hasStandardDeclaration(xml)) unsupported("standard");
}

export async function probePdf(
  bytes: Uint8Array,
  mode: "strict" | "preview" | "combine" = "strict",
  stage: (text: string) => void = () => {},
): Promise<ProbeResult> {
  try {
    const unsupported = new Set<Reason>();
    const previewFeatures = new Set<Reason>();
    // Keep checking all objects so later scripts/signatures aren't hidden by a link.
    function flag(reason: Reason): void {
      if (reason === "malformed") reject(reason);
      if (
        (mode === "combine" &&
          ["navigation", "layers", "tagged"].includes(reason)) ||
        (mode === "preview" &&
          (reason === "navigation" ||
            reason === "layers" ||
            reason === "tagged" ||
            reason === "standard"))
      ) {
        previewFeatures.add(reason);
        return;
      }
      unsupported.add(reason);
    }
    validateSize(bytes.byteLength);
    if (!new TextDecoder().decode(bytes.subarray(0, 8)).match(/^%PDF-[12]\.\d/))
      throw new ProbeFailure("INVALID_INPUT", "malformed");
    // Require an intact terminator; pdf-lib otherwise repairs some truncated files.
    if (
      !/%%EOF\s*$/.test(
        new TextDecoder().decode(
          bytes.subarray(Math.max(0, bytes.length - 1024)),
        ),
      )
    )
      throw new ProbeFailure("INVALID_INPUT", "malformed");
    const doc = await PDFDocument.load(bytes, {
      updateMetadata: false,
      throwOnInvalidObject: true,
    });
    if (
      mode !== "preview" &&
      Reflect.get(doc.context, "smartworksAmbiguousDictionary")
    )
      throw new ProbeFailure("UNSUPPORTED_PDF", "malformed");
    if (mode !== "strict") normalizeOptionalTagIndexes(doc);
    const objects = doc.context.enumerateIndirectObjects();
    // A signed AcroForm may also use unsupported field types. Report the
    // certificate restriction first instead of a misleading generic form error.
    if (
      objects.some(
        ([, value]) =>
          value instanceof PDFDict && value.has(PDFName.of("ByteRange")),
      )
    )
      throw new ProbeFailure("UNSUPPORTED_PDF", "signature");
    let intentPlan: ReturnType<typeof outputIntents>;
    if (mode !== "strict") {
      try {
        intentPlan = outputIntents(doc);
      } catch (error) {
        // A validated colour output intent is not a conformance declaration.
        // Unsupported intent shapes retain the existing read-only warning;
        // actual PDF/A, PDF/X and PDF/UA claims are still detected separately.
        if (
          mode !== "preview" ||
          !(error instanceof ProbeFailure) ||
          error.reason !== "standard"
        )
          throw error;
      }
    }
    const formPlan = mode === "strict" ? undefined : flatForm(doc);
    const inertForm = formPlan?.form;
    let attachments: ReturnType<typeof inspectAttachments> | undefined;
    if (mode !== "strict") {
      try {
        attachments = inspectAttachments(doc);
      } catch (error) {
        if (error instanceof ProbeFailure) throw error;
        throw new ProbeFailure("UNSUPPORTED_PDF", "attachments");
      }
    }
    if (objects.length > LIMITS.objects)
      throw new ProbeFailure("RESOURCE_LIMIT", "complexity");
    const seen = new Set<PDFObject>();
    const checkedStreams = new Set<PDFRawStream>();
    let nodes = 0;
    function resolve(value: PDFObject | undefined): PDFObject | undefined {
      if (!(value instanceof PDFRef)) return value;
      const target = doc.context.lookup(value);
      if (!target) throw new ProbeFailure("INVALID_INPUT", "missingReference");
      return target;
    }
    stage("Checking PDF structure…");
    function passiveAction(dict: PDFDict): boolean {
      if (mode === "strict" || dict.has(PDFName.of("Next"))) return false;
      const kind = name(resolve(dict.get(PDFName.of("S"))));
      if (kind === "GoTo") {
        const destination = resolve(dict.get(PDFName.of("D")));
        return (
          destination instanceof PDFName ||
          destination instanceof PDFString ||
          destination instanceof PDFHexString ||
          isInitialDestination(destination)
        );
      }
      if (kind !== "URI") return false;
      const uri = resolve(dict.get(PDFName.of("URI")));
      if (!(uri instanceof PDFString || uri instanceof PDFHexString))
        return false;
      const uriKind = passiveUriKind(uri.decodeText());
      return (
        !!uriKind &&
        (uriKind !== "relative" || !doc.catalog.has(PDFName.of("URI")))
      );
    }
    function isInitialDestination(value: PDFObject | undefined): boolean {
      if (!(value instanceof PDFArray) || value.size() < 2) return false;
      const page = resolve(value.get(0));
      if (
        !(page instanceof PDFDict) ||
        name(resolve(page.get(PDFName.of("Type")))) !== "Page"
      )
        return false;
      const mode = name(resolve(value.get(1)));
      const sizes: Record<string, number> = {
        XYZ: 5,
        Fit: 2,
        FitH: 3,
        FitV: 3,
        FitR: 6,
        FitB: 2,
        FitBH: 3,
        FitBV: 3,
      };
      if (sizes[mode] !== value.size()) return false;
      for (let i = 2; i < value.size(); i++) {
        const coordinate = resolve(value.get(i));
        if (coordinate === PDFNull && mode !== "FitR") continue;
        if (
          !(coordinate instanceof PDFNumber) ||
          !Number.isFinite(coordinate.asNumber())
        )
          return false;
      }
      return true;
    }
    // Type is optional on structure elements. Establish context through the K tree,
    // rather than trusting an /O Layout key on an arbitrary action dictionary.
    const structureElements = new Set<PDFDict>();
    const structureSeen = new Set<PDFObject>();
    function indexStructure(raw: PDFObject | undefined, depth = 0): void {
      const obj = resolve(raw);
      if (!obj || structureSeen.has(obj)) return;
      if (depth > LIMITS.depth || structureSeen.size >= LIMITS.nodes)
        throw new ProbeFailure("RESOURCE_LIMIT", "complexity");
      structureSeen.add(obj);
      if (obj instanceof PDFArray) {
        for (let i = 0; i < obj.size(); i++) indexStructure(obj.get(i), depth);
      } else if (obj instanceof PDFDict) {
        if (obj.has(PDFName.of("S"))) {
          structureElements.add(obj);
          indexStructure(obj.get(PDFName.of("P")), depth + 1);
        }
        indexStructure(obj.get(PDFName.of("K")), depth + 1);
      }
    }
    indexStructure(doc.catalog.get(PDFName.of("StructTreeRoot")));
    // ParentTree may index leaf elements absent from the reading-order K tree.
    // Their A entry is still a structure attribute; recursively inspect its
    // contents below so scripts cannot hide behind this contextual distinction.
    const tagRoot = resolve(doc.catalog.get(PDFName.of("StructTreeRoot")));
    const parentTrees = new Set<PDFDict>();
    function indexParents(raw: PDFObject | undefined, depth = 0): void {
      const tree = resolve(raw);
      if (!(tree instanceof PDFDict) || parentTrees.has(tree)) return;
      if (depth > LIMITS.depth || parentTrees.size >= LIMITS.nodes)
        throw new ProbeFailure("RESOURCE_LIMIT", "complexity");
      parentTrees.add(tree);
      const nums = resolve(tree.get(PDFName.of("Nums")));
      if (nums instanceof PDFArray)
        for (let i = 1; i < nums.size(); i += 2) indexStructure(nums.get(i));
      const kids = resolve(tree.get(PDFName.of("Kids")));
      if (kids instanceof PDFArray)
        for (let i = 0; i < kids.size(); i++)
          indexParents(kids.get(i), depth + 1);
    }
    if (tagRoot instanceof PDFDict)
      indexParents(tagRoot.get(PDFName.of("ParentTree")));

    const pages = doc.getPages();
    const contentStreams = new Set<PDFRawStream>();
    const addContent = (value: PDFObject | undefined) => {
      const content = resolve(value);
      if (content instanceof PDFRawStream) contentStreams.add(content);
      else if (content instanceof PDFArray) {
        for (let i = 0; i < content.size(); i++) {
          const stream = resolve(content.get(i));
          if (!(stream instanceof PDFRawStream)) reject("malformed");
          contentStreams.add(stream);
        }
      }
    };
    for (const page of pages) addContent(page.node.get(PDFName.of("Contents")));
    for (const [, object] of objects) {
      if (!(object instanceof PDFDict)) continue;
      const glyphs = resolve(object.get(PDFName.of("CharProcs")));
      if (glyphs instanceof PDFDict)
        for (const [, value] of glyphs.entries()) addContent(value);
    }
    function visit(raw: PDFObject, depth: number): void {
      const obj = resolve(raw);
      if (!obj || seen.has(obj)) return;
      if (++nodes > LIMITS.nodes || depth > LIMITS.depth)
        throw new ProbeFailure("RESOURCE_LIMIT", "complexity");
      seen.add(obj);
      if (obj instanceof PDFInvalidObject)
        throw new ProbeFailure("INVALID_INPUT", "malformed");
      if (obj instanceof PDFArray) {
        for (let i = 0; i < obj.size(); i++) visit(obj.get(i), depth + 1);
        return;
      }
      const dict =
        obj instanceof PDFRawStream
          ? obj.dict
          : obj instanceof PDFDict
            ? obj
            : undefined;
      if (!dict) return;
      const type = name(resolve(dict.get(PDFName.of("Type"))));
      const subtype = name(resolve(dict.get(PDFName.of("Subtype"))));
      if (obj instanceof PDFRawStream && !checkedStreams.has(obj)) {
        checkedStreams.add(obj);
        const filter = resolve(dict.get(PDFName.of("Filter")));
        const singleFilter =
          filter instanceof PDFArray && filter.size() > 0
            ? resolve(filter.get(filter.size() - 1))
            : filter;
        const nativeImage =
          subtype === "Image" &&
          ["DCTDecode", "JPXDecode", "CCITTFaxDecode", "JBIG2Decode"].includes(
            name(singleFilter),
          );
        // PDF images may wrap JPEG/JPX/fax bytes in lossless filters. Check
        // those wrappers with the same bounded decoder; PDF.js handles the
        // final image codec. pdf-lib cannot decode that final codec itself.
        let nativeBytes = obj.contents;
        if (nativeImage && filter instanceof PDFArray && filter.size() > 1) {
          const wrapper = dict.clone();
          wrapper.set(
            PDFName.of("Filter"),
            doc.context.obj(filter.asArray().slice(0, -1)),
          );
          const params = resolve(dict.get(PDFName.of("DecodeParms")));
          if (params instanceof PDFArray)
            wrapper.set(
              PDFName.of("DecodeParms"),
              doc.context.obj(params.asArray().slice(0, -1)),
            );
          else if (params && params !== PDFNull) reject("malformed");
          const decoded = decodePDFRawStream(
            PDFRawStream.of(wrapper, obj.contents),
          ).decode();
          if (decoded.length > LIMITS.decodedImageBytes)
            throw new ProbeFailure("RESOURCE_LIMIT", "complexity");
          nativeBytes = decoded;
        }
        if (nativeImage && name(singleFilter) === "DCTDecode") {
          const w = resolve(dict.get(PDFName.of("Width")));
          const h = resolve(dict.get(PDFName.of("Height")));
          if (!(w instanceof PDFNumber) || !(h instanceof PDFNumber))
            reject("malformed");
          checkJpegDimensions(nativeBytes, w.asNumber(), h.asNumber());
        }
        if (!nativeImage && type !== "Metadata" && !streamedImages.has(obj)) {
          // The pinned decoder patch checks allocation *before* decompressing;
          // this also preflights page/font/form streams before PDF.js sees them.
          const decoded = decodePDFRawStream(obj).decode();
          if (
            decoded.length >
            (subtype === "Image"
              ? LIMITS.decodedImageBytes
              : LIMITS.decodedStreamBytes)
          )
            throw new ProbeFailure("RESOURCE_LIMIT", "complexity");
          if (
            contentStreams.has(obj) ||
            subtype === "Form" ||
            type === "Pattern"
          )
            imageWork += inspectInlineImages(
              decoded,
              LIMITS.streamedImageWorkBytes - imageWork,
            );
        }
      }
      if (type === "Sig" || type === "DocTimeStamp") flag("signature");
      if (type === "Action" && !passiveAction(dict)) flag("actions");
      if (
        (type === "Filespec" && !attachments?.files.has(dict)) ||
        (type === "EmbeddedFile" && !attachments?.streams.has(dict))
      )
        flag("attachments");
      if (type === "OCG" || type === "OCMD") flag("layers");
      if (["RichMedia", "Movie", "Sound", "3D", "Screen"].includes(subtype))
        flag("multimedia");
      if (actionTypes.has(name(resolve(dict.get(PDFName.of("S")))))) {
        if (passiveAction(dict)) previewFeatures.add("navigation");
        else flag("actions");
      }
      if (subtype === "Image") {
        const w = resolve(dict.get(PDFName.of("Width")));
        const h = resolve(dict.get(PDFName.of("Height")));
        if (
          !(w instanceof PDFNumber) ||
          !(h instanceof PDFNumber) ||
          w.asNumber() <= 0 ||
          h.asNumber() <= 0
        )
          reject("malformed");
        const f = resolve(dict.get(PDFName.of("Filter")));
        const finalFilter =
          f instanceof PDFArray ? resolve(f.get(f.size() - 1)) : f;
        const imageLimit =
          name(finalFilter) === "DCTDecode"
            ? LIMITS.jpegPixels
            : LIMITS.imagePixels;
        if (w.asNumber() * h.asNumber() > imageLimit)
          throw new ProbeFailure("RESOURCE_LIMIT", "image");
      }
      if (type === "Metadata") {
        if (!(obj instanceof PDFRawStream)) reject("malformed");
        inspectMetadata(obj, flag);
      }
      for (const [key, value] of dict.entries()) {
        const k = key.decodeText();
        if (
          obj instanceof PDFRawStream &&
          ["F", "FFilter", "FDecodeParms"].includes(k)
        )
          flag("attachments");
        if (k === "Metadata") {
          const metadata = resolve(value);
          if (!(metadata instanceof PDFRawStream)) reject("malformed");
          inspectMetadata(metadata, flag);
        }
        if (k === "FT" && name(resolve(value)) === "Sig") flag("signature");
        if (k === "SigFlags") {
          const bits = resolve(value);
          if (!(bits instanceof PDFNumber) || bits.asNumber() !== 0)
            flag("signature");
        }
        const reason = forbiddenKeys[k];
        if (
          reason &&
          !(
            k === "OutputIntents" &&
            dict === doc.catalog &&
            intentPlan?.array === resolve(value)
          ) &&
          !(k === "FT" && formPlan?.widgets.has(dict)) &&
          !(
            attachments &&
            ((k === "EmbeddedFiles" && dict === attachments.names) ||
              (k === "AF" && dict === doc.catalog) ||
              (k === "EF" && attachments.files.has(dict)))
          ) &&
          !(
            k === "AcroForm" &&
            dict === doc.catalog &&
            inertForm &&
            resolve(value) === inertForm
          )
        )
          flag(reason);
        if (k === "Annots") {
          const annotations = resolve(value);
          if (!(annotations instanceof PDFArray)) reject("malformed");
          for (let i = 0; i < annotations.size(); i++) {
            const annotation = resolve(annotations.get(i));
            if (
              mode !== "strict" &&
              annotation instanceof PDFDict &&
              (passiveAnnotations.has(
                name(resolve(annotation.get(PDFName.of("Subtype")))),
              ) ||
                !!formPlan?.widgets.has(annotation))
            )
              previewFeatures.add("annotations");
            else flag("annotations");
          }
        }
        if (k === "OpenAction") {
          const destination = resolve(value);
          if (!isInitialDestination(destination)) flag("actions");
        }
        if (k === "A" && resolve(value) instanceof PDFDict) {
          // A on a structure element means attributes, not an action.
          // Continue walking the value: a disguised script must still be rejected.
          if (type === "StructElem" || structureElements.has(dict))
            flag("tagged");
          else if (passiveAction(resolve(value) as PDFDict))
            previewFeatures.add("navigation");
          else flag("actions");
        }
        if (
          (value instanceof PDFString || value instanceof PDFHexString) &&
          k.startsWith("GTS_PDF")
        )
          flag("standard");
        visit(value, depth + 1);
      }
    }
    const streamedImages = new Set<PDFRawStream>();
    let imageWork = 0;
    for (const [, object] of objects) {
      if (!(object instanceof PDFRawStream)) continue;
      const dict = object.dict;
      if (name(resolve(dict.get(PDFName.of("Subtype")))) !== "Image") continue;
      const filter = resolve(dict.get(PDFName.of("Filter")));
      const filters =
        filter instanceof PDFArray
          ? filter.asArray().map((v) => name(resolve(v)))
          : [name(filter)];
      if (
        filters.at(-1) !== "FlateDecode" ||
        !filters
          .slice(0, -1)
          .every((v) => ["ASCII85Decode", "ASCIIHexDecode"].includes(v))
      )
        continue;
      const w = resolve(dict.get(PDFName.of("Width")));
      const h = resolve(dict.get(PDFName.of("Height")));
      if (
        !(w instanceof PDFNumber) ||
        !(h instanceof PDFNumber) ||
        !Number.isSafeInteger(w.asNumber()) ||
        !Number.isSafeInteger(h.asNumber()) ||
        w.asNumber() <= 0 ||
        h.asNumber() <= 0
      )
        reject("malformed");
      if (w.asNumber() * h.asNumber() > LIMITS.imagePixels)
        throw new ProbeFailure("RESOURCE_LIMIT", "image");
      let compressed = object.contents;
      if (filters.length > 1) {
        const wrapper = dict.clone();
        wrapper.set(
          PDFName.of("Filter"),
          doc.context.obj(filters.slice(0, -1)),
        );
        wrapper.delete(PDFName.of("DecodeParms"));
        compressed = decodePDFRawStream(
          PDFRawStream.of(wrapper, compressed),
        ).decode();
        if (compressed.length > LIMITS.bytes)
          throw new ProbeFailure("RESOURCE_LIMIT", "complexity");
      }
      imageWork += await checkFlateImage(
        compressed,
        LIMITS.streamedImageWorkBytes - imageWork,
      );
      if (imageWork > LIMITS.streamedImageWorkBytes)
        throw new ProbeFailure("RESOURCE_LIMIT", "complexity");
      streamedImages.add(object);
    }
    for (const [, object] of objects) visit(object, 0);
    visit(doc.catalog, 0);
    if (doc.context.trailerInfo.Info) visit(doc.context.trailerInfo.Info, 0);
    if (pages.length < 1) throw new ProbeFailure("INVALID_INPUT", "pages");
    if (pages.length > LIMITS.pages)
      throw new ProbeFailure("RESOURCE_LIMIT", "pages");
    for (const page of pages) {
      const unitObj = resolve(page.node.get(PDFName.of("UserUnit")));
      const unit =
        unitObj instanceof PDFNumber ? unitObj.asNumber() : unitObj ? NaN : 1;
      const rotation = page.getRotation().angle;
      if (
        !Number.isFinite(unit) ||
        unit <= 0 ||
        !Number.isFinite(rotation) ||
        rotation % 90 !== 0
      )
        reject("malformed");
      for (const box of [page.getMediaBox(), page.getCropBox()]) {
        if (
          ![box.x, box.y, box.width, box.height].every(Number.isFinite) ||
          box.width <= 0 ||
          box.height <= 0
        )
          reject("malformed");
        if (
          box.width * unit > LIMITS.pagePoints ||
          box.height * unit > LIMITS.pagePoints
        )
          throw new ProbeFailure("RESOURCE_LIMIT", "geometry");
      }
    }
    if (unsupported.size) {
      const reasons = [...unsupported];
      return {
        ok: false,
        code: "UNSUPPORTED_PDF",
        reason: reasons[0],
        reasons,
      };
    }
    return {
      ok: true,
      pages: pages.length,
      byteLength: bytes.byteLength,
      ...(previewFeatures.size
        ? { previewFeatures: [...previewFeatures] }
        : {}),
    };
  } catch (error) {
    if (error instanceof Error && error.message === "SMARTWORKS_RESOURCE_LIMIT")
      return { ok: false, code: "RESOURCE_LIMIT", reason: "complexity" };
    // pdf-lib's ES5 Error subclasses do not consistently preserve instanceof.
    if (
      error instanceof EncryptedPDFError ||
      (error instanceof Error &&
        error.message ===
          "Input document to `PDFDocument.load` is encrypted. You can use `PDFDocument.load(..., { ignoreEncryption: true })` if you wish to load the document anyways.")
    )
      return { ok: false, code: "UNSUPPORTED_PDF", reason: "encrypted" };
    return failure(error);
  }
}
