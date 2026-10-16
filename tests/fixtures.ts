import {
  PDFDocument,
  PDFName,
  PDFString,
  PDFObject,
  StandardFonts,
  rgb,
  degrees,
} from "pdf-lib";
export const cases = {
  form: "form",
  xfa: "form",
  signature: "signature",
  annotations: "annotations",
  attachment: "attachments",
  portfolio: "attachments",
  javascript: "actions",
  launch: "actions",
  layers: "layers",
  bookmarks: "navigation",
  labels: "navigation",
  destinations: "navigation",
  tagged: "tagged",
  pdfa: "standard",
  pdfx: "standard",
  multimedia: "multimedia",
} as const;
export type FixtureKind =
  | keyof typeof cases
  | "plain"
  | "empty-annots"
  | "geometry"
  | "huge-page"
  | "huge-image"
  | "zero-pages"
  | "too-many-pages"
  | "max-pages"
  | "broken-ref"
  | "encrypted-marker"
  | "metadata"
  | "deep"
  | "token-text";

export async function makeFixture(
  kind: FixtureKind = "plain",
  objectStreams = true,
): Promise<Uint8Array> {
  const doc = await PDFDocument.create();
  doc.setCreationDate(new Date("2026-10-06T00:00:00Z"));
  doc.setModificationDate(new Date("2026-10-06T00:00:00Z"));
  const font = await doc.embedFont(StandardFonts.Helvetica);
  const count =
    kind === "zero-pages"
      ? 0
      : kind === "too-many-pages"
        ? 201
        : kind === "max-pages"
          ? 200
          : 2;
  for (let i = 0; i < count; i++) {
    const p = doc.addPage([595, 842]);
    p.drawRectangle({
      x: 40,
      y: 40,
      width: 515,
      height: 762,
      borderWidth: 1,
      borderColor: rgb(0.2, 0.4, 0.3),
    });
    p.drawText("SMARTWORKS / LOCAL PREVIEW", {
      x: 62,
      y: 756,
      font,
      size: 12,
      color: rgb(0.2, 0.4, 0.3),
    });
    p.drawText(`A quieter way to work.`, { x: 62, y: 690, font, size: 27 });
    p.drawText(`Synthetic test document - page ${i + 1} of ${count}`, {
      x: 62,
      y: 649,
      font,
      size: 13,
    });
    p.drawText("PRIVATE_TEST_MARKER_20261006", {
      x: 62,
      y: 608,
      font,
      size: 11,
    });
    p.drawText("This sample contains no personal information.", {
      x: 62,
      y: 582,
      font,
      size: 11,
    });
    if (kind === "token-text")
      p.drawText("/JavaScript /AcroForm /Encrypt are just text here.", {
        x: 62,
        y: 550,
        font,
        size: 11,
      });
  }
  const ctx = doc.context;
  type Literal =
    | string
    | number
    | boolean
    | null
    | PDFObject
    | Literal[]
    | { [key: string]: Literal };
  const set = (key: string, value: Literal) =>
    doc.catalog.set(
      PDFName.of(key),
      ctx.obj({ value }).get(PDFName.of("value"))!,
    );
  const page = doc.getPages()[0];
  switch (kind) {
    case "form":
      set("AcroForm", {
        Fields: [
          ctx.register(
            ctx.obj({
              FT: "Tx",
              T: PDFString.of("Example"),
              V: PDFString.of("A value"),
            }),
          ),
        ],
      });
      break;
    case "xfa":
      set("AcroForm", { XFA: PDFString.of("<xdp/>"), Fields: [] });
      break;
    case "signature":
      ctx.register(
        ctx.obj({
          Type: "Sig",
          ByteRange: [0, 10, 20, 30],
          Contents: PDFString.of("synthetic signature dictionary"),
        }),
      );
      break;
    case "annotations":
      page?.node.set(
        PDFName.of("Annots"),
        ctx.obj([
          ctx.obj({ Type: "Annot", Subtype: "Text", Rect: [10, 10, 30, 30] }),
        ]),
      );
      break;
    case "empty-annots":
      page?.node.set(PDFName.of("Annots"), ctx.obj([]));
      break;
    case "attachment":
      set("Names", { EmbeddedFiles: { Names: [] } });
      break;
    case "portfolio":
      set("Collection", {});
      break;
    case "javascript":
      set("OpenAction", {
        S: "JavaScript",
        JS: PDFString.of('app.alert("synthetic")'),
      });
      break;
    case "launch":
      set("OpenAction", { S: "Launch", F: PDFString.of("never-open.txt") });
      break;
    case "layers":
      set("OCProperties", { OCGs: [] });
      break;
    case "bookmarks":
      set("Outlines", { Type: "Outlines", Count: 0 });
      break;
    case "labels":
      set("PageLabels", { Nums: [0, { S: "D" }] });
      break;
    case "destinations":
      set("Names", { Dests: { Names: [] } });
      break;
    case "tagged":
      set("MarkInfo", { Marked: true });
      set("StructTreeRoot", { Type: "StructTreeRoot" });
      break;
    case "pdfa":
    case "metadata": {
      const xml =
        kind === "pdfa"
          ? '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/" pdfaid:part="2"/></rdf:RDF></x:xmpmeta>'
          : '<x:xmpmeta xmlns:x="adobe:ns:meta/"><title>Ordinary metadata</title></x:xmpmeta>';
      set(
        "Metadata",
        ctx.register(
          ctx.flateStream(xml, { Type: "Metadata", Subtype: "XML" }),
        ),
      );
      break;
    }
    case "pdfx":
      set("OutputIntents", [{ Type: "OutputIntent", S: "GTS_PDFX" }]);
      break;
    case "multimedia":
      ctx.register(ctx.obj({ Type: "Annot", Subtype: "RichMedia" }));
      break;
    case "huge-page":
      page?.setSize(20_000, 1000);
      break;
    case "huge-image":
      ctx.register(
        ctx.stream("", {
          Type: "XObject",
          Subtype: "Image",
          Width: 5000,
          Height: 5000,
          BitsPerComponent: 8,
          ColorSpace: "DeviceRGB",
        }),
      );
      break;
    case "geometry":
      page?.setRotation(degrees(90));
      page?.setCropBox(30, 50, 400, 600);
      page?.node.set(PDFName.of("UserUnit"), ctx.obj(2));
      break;
    case "broken-ref":
      set("Broken", ctx.nextRef());
      break;
    case "encrypted-marker":
      ctx.trailerInfo.Encrypt = ctx.register(
        ctx.obj({ Filter: "Standard", V: 1, R: 2 }),
      );
      break;
    case "deep": {
      let value = ctx.obj({ Leaf: 1 });
      for (let i = 0; i < 110; i++) value = ctx.obj({ Nested: value });
      set("Deep", value);
      break;
    }
  }
  return doc.save({ useObjectStreams: objectStreams, addDefaultPage: false });
}
