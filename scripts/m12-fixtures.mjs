import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import createQpdf from "@neslinesli93/qpdf-wasm";
import { PDFDocument, PDFName, PDFString, PDFDict } from "pdf-lib";
import { deflateSync } from "node:zlib";

/** Synthetic sources only. Generated encrypted files never enter Git. */
export async function generateUnlockFixtures() {
  const folder = "tests/fixtures/m12";
  await fs.mkdir(folder, { recursive: true });
  const engine = await createQpdf({
    locateFile: () =>
      pathToFileURL(
        path.resolve("node_modules/@neslinesli93/qpdf-wasm/dist/qpdf.wasm"),
      ).href,
    noInitialRun: true,
    noFSInit: true,
    preRun: [
      (m) =>
        m.FS.init(
          () => null,
          () => {},
          () => {},
        ),
    ],
  });
  const source = await fs.readFile("tests/fixtures/m5/normal-a4.pdf");
  async function encrypt(
    name,
    bytes,
    {
      user = "synthetic-user",
      owner = "synthetic-owner",
      bits = "256",
      options = [],
    } = {},
  ) {
    engine.FS.writeFile("/input.pdf", bytes);
    const code = engine.callMain([
      "--allow-weak-crypto",
      "--encrypt",
      user,
      owner,
      bits,
      ...options,
      "--",
      "/input.pdf",
      "/output.pdf",
    ]);
    if (code !== 0) throw Error("Synthetic unlock fixture generation failed");
    await fs.writeFile(
      `${folder}/${name}.pdf`,
      engine.FS.readFile("/output.pdf"),
    );
    engine.FS.unlink("/input.pdf");
    engine.FS.unlink("/output.pdf");
  }
  for (const [id, bits, options] of [
    ["rc4-40", "40", []],
    ["rc4-128", "128", ["--use-aes=n"]],
    ["aes-128", "128", ["--use-aes=y"]],
    ["aes-256", "256", []],
    ["r5", "256", ["--force-R5"]],
  ])
    await encrypt(id, source, { bits, options });
  await encrypt("unicode", source, {
    user: "合成 密碼✓",
    owner: "所有者 密碼✓",
  });
  await encrypt("empty-user", source, { user: "" });
  await encrypt("legacy-encoding", source, {
    user: "é space",
    owner: "Ö owner",
    bits: "128",
    options: ["--use-aes=y"],
  });
  await encrypt("special", source, { user: "  \"quote'=合成✓  " });
  for (const name of [
    "normal-a4",
    "mixed-page-size",
    "landscape",
    "100-pages",
    "200-pages",
    "scanned",
    "form",
    "chinese",
    "japanese",
    "image-heavy",
  ])
    await encrypt(
      "reg-" + name,
      await fs.readFile(`tests/fixtures/m5/${name}.pdf`),
    );
  for (const [name, input] of [
    ["navigation", "navigation-a"],
    ["layers", "layer-on"],
    ["tags", "final-tags"],
    ["attachments", "final-attachment"],
  ])
    await encrypt(
      name,
      await fs.readFile(`tests/fixtures/combine/${input}.pdf`),
    );
  for (const name of ["signature", "credentials", "standard", "zero"]) {
    const doc =
      name === "zero"
        ? await PDFDocument.create()
        : await PDFDocument.load(source);
    if (name === "signature")
      doc.catalog.set(
        PDFName.of("Perms"),
        doc.context.obj({
          DocMDP: doc.context.register(
            doc.context.obj({ Type: "Sig", ByteRange: [0, 10, 20, 30] }),
          ),
        }),
      );
    if (name === "credentials") {
      const embedded = doc.context.register(
        doc.context.flateStream(new Uint8Array([1, 2, 3]), {
          Type: "EmbeddedFile",
          Subtype: "application/c2pa",
        }),
      );
      const file = doc.context.register(
        doc.context.obj({
          Type: "Filespec",
          F: PDFString.of("synthetic.c2pa"),
          AFRelationship: "C2PA_Manifest",
          EF: { F: embedded },
        }),
      );
      doc.catalog.set(PDFName.of("AF"), doc.context.obj([file]));
    }
    if (name === "standard") {
      const info = doc.context.lookup(doc.context.trailerInfo.Info);
      if (!(info instanceof PDFDict)) throw Error("Missing synthetic Info");
      info.set(PDFName.of("GTS_PDFXVersion"), PDFString.of("PDF/X-4"));
    }
    await encrypt(name, await doc.save({ addDefaultPage: false }));
  }
  const encrypted = await fs.readFile(`${folder}/aes-256.pdf`);
  await fs.writeFile(
    `${folder}/handler.pdf`,
    Buffer.from(
      encrypted.toString("latin1").replace("/Standard", "/PubSecXX"),
      "latin1",
    ),
  );
  await fs.writeFile(
    `${folder}/revision.pdf`,
    Buffer.from(
      encrypted.toString("latin1").replace(/\/R\s+6\b/, "/R 9"),
      "latin1",
    ),
  );
  console.log("Prepared synthetic unlock fixtures.");
}
/** One tiny encrypted file expands to a deliberately excessive object stream.
 * Handwritten synthetic syntax avoids allocating a huge UTF-16 authoring tree. */
export async function generateDenseUnlockFixture() {
  const pieces = [Buffer.from("%PDF-1.7\n%\xff\xff\xff\xff\n", "latin1")],
    offsets = new Map();
  let position = pieces[0].length;
  const add = (number, body) => {
    offsets.set(number, position);
    const bytes = Buffer.concat([
      Buffer.from(`${number} 0 obj\n`),
      Buffer.isBuffer(body) ? body : Buffer.from(body),
      Buffer.from("\nendobj\n"),
    ]);
    pieces.push(bytes);
    position += bytes.length;
  };
  add(1, "<< /Type /Catalog /Pages 2 0 R >>");
  add(2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>");
  add(
    3,
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Resources << >> /Contents 4 0 R >>",
  );
  add(4, "<< /Length 0 >>\nstream\n\nendstream");
  const compressed = deflateSync(
    Buffer.concat([
      Buffer.from("5 0 << /Subject ("),
      Buffer.alloc(64 * 1024 * 1024, 65),
      Buffer.from(") >>"),
    ]),
  );
  add(
    6,
    Buffer.concat([
      Buffer.from(
        `<< /Type /ObjStm /N 1 /First 4 /Filter /FlateDecode /Length ${compressed.length} >>\nstream\n`,
      ),
      compressed,
      Buffer.from("\nendstream"),
    ]),
  );
  const xref = position,
    entries = Buffer.alloc(8 * 7);
  for (let id = 0; id < 8; id++) {
    const index = id * 7;
    entries[index] = id === 0 ? 0 : id === 5 ? 2 : 1;
    entries.writeUInt32BE(
      id === 0 ? 0 : id === 5 ? 6 : id === 7 ? xref : offsets.get(id),
      index + 1,
    );
    entries.writeUInt16BE(id === 0 ? 65535 : 0, index + 5);
  }
  add(
    7,
    Buffer.concat([
      Buffer.from(
        `<< /Type /XRef /Size 8 /Root 1 0 R /Info 5 0 R /W [1 4 2] /Length ${entries.length} >>\nstream\n`,
      ),
      entries,
      Buffer.from("\nendstream"),
    ]),
  );
  pieces.push(Buffer.from(`startxref\n${xref}\n%%EOF\n`));
  const engine = await createQpdf({
    locateFile: () =>
      pathToFileURL(
        path.resolve("node_modules/@neslinesli93/qpdf-wasm/dist/qpdf.wasm"),
      ).href,
    noInitialRun: true,
    noFSInit: true,
    preRun: [
      (m) =>
        m.FS.init(
          () => null,
          () => {},
          () => {},
        ),
    ],
  });
  engine.FS.writeFile("/input.pdf", Buffer.concat(pieces));
  const code = engine.callMain([
    "--encrypt",
    "synthetic-user",
    "synthetic-owner",
    "256",
    "--",
    "/input.pdf",
    "/output.pdf",
  ]);
  if (code !== 0) throw Error("Dense synthetic PDF generation failed");
  await fs.mkdir("tests/fixtures/m12", { recursive: true });
  await fs.writeFile(
    "tests/fixtures/m12/dense.pdf",
    engine.FS.readFile("/output.pdf"),
  );
  engine.FS.unlink("/input.pdf");
  engine.FS.unlink("/output.pdf");
  console.log("Prepared synthetic resource-boundary PDF.");
}
if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href
)
  if (process.argv.includes("--dense")) await generateDenseUnlockFixture();
  else await generateUnlockFixtures();
