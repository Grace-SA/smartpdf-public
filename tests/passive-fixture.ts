import { PDFDocument, PDFName, PDFString } from "pdf-lib";

// Entirely synthetic. No real sample content or URLs are retained in fixtures.
export async function passiveFixture() {
  const doc = await PDFDocument.create();
  const page = doc.addPage([400, 800]);
  const ctx = doc.context;
  const visible = ctx.register(
    ctx.obj({ Type: "OCG", Name: PDFString.of("Visible") }),
  );
  const hidden = ctx.register(
    ctx.obj({ Type: "OCG", Name: PDFString.of("Hidden") }),
  );
  doc.catalog.set(
    PDFName.of("OCProperties"),
    ctx.obj({
      OCGs: [visible, hidden],
      D: { BaseState: "ON", OFF: [hidden], Order: [visible, hidden] },
    }),
  );
  page.node.set(
    PDFName.of("Resources"),
    ctx.obj({ Properties: { Visible: visible, Hidden: hidden } }),
  );
  page.node.addContentStream(
    ctx.register(
      ctx.flateStream(
        "q /OC /Visible BDC 0 1 0 rg 50 600 100 100 re f EMC /OC /Hidden BDC 1 0 0 rg 200 600 100 100 re f EMC Q",
      ),
    ),
  );
  page.node.set(
    PDFName.of("Annots"),
    ctx.obj([
      ctx.register(
        ctx.obj({
          Type: "Annot",
          Subtype: "Link",
          Rect: [50, 600, 150, 700],
          Border: [0, 0, 1],
          A: {
            Type: "Action",
            S: "URI",
            URI: PDFString.of("https://example.invalid/never-visit"),
          },
        }),
      ),
    ]),
  );
  doc.catalog.set(PDFName.of("PageLabels"), ctx.obj({ Nums: [0, { S: "r" }] }));
  doc.catalog.set(
    PDFName.of("Outlines"),
    ctx.obj({ Type: "Outlines", Count: 0 }),
  );
  return doc;
}
