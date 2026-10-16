import { describe, expect, it } from "vitest";
import { PDFDocument, PDFName, PDFString } from "pdf-lib";
import { probePdf } from "../src/core/probe";

describe.each([false, true])(
  "semantic feature detection, compressed=%s",
  (compressed) => {
    async function document() {
      const doc = await PDFDocument.create();
      doc.addPage();
      return doc;
    }
    async function probe(doc: PDFDocument) {
      return probePdf(await doc.save({ useObjectStreams: compressed }));
    }
    for (const mode of ["Fit", "XYZ", "FitH", "FitR"] as const) {
      it(`accepts a passive ${mode} initial destination`, async () => {
        const doc = await document();
        const coordinates =
          mode === "XYZ"
            ? [null, null, 0]
            : mode === "FitH"
              ? [null]
              : mode === "FitR"
                ? [0, 0, 100, 100]
                : [];
        doc.catalog.set(
          PDFName.of("OpenAction"),
          doc.context.register(
            doc.context.obj([doc.getPages()[0]!.ref, mode, ...coordinates]),
          ),
        );
        expect(await probe(doc)).toMatchObject({ ok: true, pages: 1 });
      });
    }
    for (const mode of [
      "JavaScript",
      "Launch",
      "GoTo",
      "UnknownVendorAction",
    ]) {
      it(`still rejects ${mode} action dictionaries`, async () => {
        const doc = await document();
        doc.catalog.set(
          PDFName.of("OpenAction"),
          doc.context.obj({ S: mode, JS: PDFString.of("synthetic") }),
        );
        expect(await probe(doc)).toMatchObject({
          ok: false,
          reasons: expect.arrayContaining(["actions"]),
        });
      });
    }
    it("does not accept invalid destinations", async () => {
      const doc = await document();
      doc.catalog.set(
        PDFName.of("OpenAction"),
        doc.context.obj([doc.getPages()[0]!.ref, "XYZ", 0]),
      );
      expect(await probe(doc)).toMatchObject({ ok: false });
      doc.catalog.set(
        PDFName.of("OpenAction"),
        doc.context.obj([
          doc.context.register(doc.context.obj({ Type: "Catalog" })),
          "Fit",
        ]),
      );
      expect(await probe(doc)).toMatchObject({ ok: false });
    });
    it("classifies structure attributes without an action false positive", async () => {
      const doc = await document();
      const elem = doc.context.obj({
        Type: "StructElem",
        S: "P",
        A: { O: "Layout", Placement: "Block" },
      });
      doc.catalog.set(
        PDFName.of("StructTreeRoot"),
        doc.context.obj({
          Type: "StructTreeRoot",
          K: doc.context.register(elem),
        }),
      );
      const result = await probe(doc);
      expect(result).toMatchObject({ ok: false, reasons: ["tagged"] });
    });
    it("does not let an attribute disguise a script", async () => {
      const doc = await document();
      doc.context.register(
        doc.context.obj({
          Type: "StructElem",
          A: { O: "Layout", S: "JavaScript", JS: PDFString.of("synthetic") },
        }),
      );
      expect(await probe(doc)).toMatchObject({
        ok: false,
        reasons: expect.arrayContaining(["tagged", "actions"]),
      });
    });
    it("recognizes an attribute owner through the structure tree without Type", async () => {
      const doc = await document();
      const elem = doc.context.register(
        doc.context.obj({ S: "P", A: { O: "Layout" } }),
      );
      doc.catalog.set(
        PDFName.of("StructTreeRoot"),
        doc.context.obj({ K: [elem] }),
      );
      expect(await probe(doc)).toMatchObject({
        ok: false,
        reasons: ["tagged"],
      });
    });
    it("does not describe zero signature flags as a signature", async () => {
      const doc = await document();
      doc.catalog.set(
        PDFName.of("AcroForm"),
        doc.context.obj({ Fields: [], SigFlags: 0 }),
      );
      expect(await probe(doc)).toMatchObject({ ok: false, reasons: ["form"] });
    });
    it("keeps unknown A dictionaries blocked outside structure elements", async () => {
      const doc = await document();
      doc
        .getPages()[0]!
        .node.set(PDFName.of("A"), doc.context.obj({ O: "Layout" }));
      expect(await probe(doc)).toMatchObject({
        ok: false,
        reasons: ["actions"],
      });
    });
    it("reports all supported feature categories, including a later script", async () => {
      const doc = await document();
      doc
        .getPages()[0]!
        .node.set(
          PDFName.of("Annots"),
          doc.context.obj([{ Subtype: "Link", Rect: [0, 0, 10, 10] }]),
        );
      doc.catalog.set(PDFName.of("AcroForm"), doc.context.obj({ Fields: [] }));
      doc.catalog.set(
        PDFName.of("OpenAction"),
        doc.context.obj({ S: "JavaScript", JS: PDFString.of("synthetic") }),
      );
      expect(await probe(doc)).toMatchObject({
        ok: false,
        reasons: expect.arrayContaining(["annotations", "form", "actions"]),
      });
    });
  },
);
