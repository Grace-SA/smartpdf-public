import { expect, it } from "vitest";
import { inspectWordBytes, crc32 } from "../src/word/preflight-core";
import { docxFixture } from "./docx-fixture";
it("rejects XML control characters, undefined entities and unbound attributes", () => {
  for (const body of [
    "<w:p><w:t>before" + String.fromCharCode(1) + "after</w:t></w:p>",
    "<w:p><w:t>&#0;</w:t></w:p>",
    "<w:p><w:t>&unknown;</w:t></w:p>",
    '<w:p invalid:attribute="x"><w:t>Text</w:t></w:p>',
  ])
    expect(
      inspectWordBytes(docxFixture(body)).issues.map((x) => x.code),
    ).toContain("MALFORMED_XML");
  expect(
    inspectWordBytes(
      docxFixture(
        '<w:p><w:r><w:t xml:space="preserve">Valid &amp; text</w:t></w:r></w:p>',
      ),
    ).issues,
  ).toEqual([]);
});
const codes = (body: string, extra = {}) =>
  inspectWordBytes(docxFixture(body, extra)).issues.map((x) => x.code);
it("reads stored and deflated OOXML without network or content in results", () => {
  expect(crc32(new TextEncoder().encode("123456789"))).toBe(0xcbf43926);
  for (const compressed of [true, false]) {
    const result = inspectWordBytes(
      docxFixture(
        "<w:p><w:r><w:t>PRIVATE_SYNTHETIC_BODY</w:t></w:r></w:p>",
        {},
        compressed,
      ),
    );
    expect(result.issues).toEqual([]);
    expect(JSON.stringify(result)).not.toContain("PRIVATE_SYNTHETIC_BODY");
  }
});
it("allows web view hiding, disabled hiding and DrawingML path moves", () => {
  expect(
    codes(
      '<w:p><w:r><w:rPr><w:webHidden/><w:vanish w:val="false"/></w:rPr><w:t>Visible</w:t><w:drawing xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:moveTo/></w:drawing></w:r></w:p>',
    ),
  ).toEqual([]);
});
it("distinguishes revisions, comments, active hidden text and embedded fonts", () => {
  const result = codes(
    "<w:p><w:ins><w:r><w:t>Inserted</w:t></w:r></w:ins><w:commentRangeStart/><w:r><w:rPr><w:vanish/></w:rPr></w:r></w:p>",
    { "word/fonts/fixture.odttf": "synthetic" },
  );
  expect(result).toEqual(
    expect.arrayContaining([
      "TRACKED_CHANGES",
      "COMMENTS",
      "HIDDEN_TEXT",
      "EMBEDDED_FONTS",
    ]),
  );
});
it("retains inherited hidden formatting and all XML declaration limits", () => {
  expect(
    codes(
      '<w:p><w:r><w:rPr><w:vanish w:val="0"/></w:rPr><w:t>Text</w:t></w:r></w:p>',
      {
        "word/styles.xml":
          '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:style><w:rPr><w:vanish/></w:rPr></w:style></w:styles>',
      },
    ),
  ).toContain("HIDDEN_TEXT");
  expect(
    codes("<w:p><w:t>Text</w:t></w:p>", {
      "customXml/item.xml": "<!DOCTYPE x><x/>",
    }),
  ).toContain("UNSAFE_PACKAGE");
});
it("rejects file links and external fields including split instructions", () => {
  expect(
    codes(
      "<w:p><w:r><w:instrText>DDE</w:instrText></w:r><w:r><w:instrText>AUTO external</w:instrText></w:r></w:p>",
    ),
  ).toContain("EXTERNAL_DATA_FIELDS");
  expect(
    codes("<w:p><w:r><w:t>Text</w:t></w:r></w:p>", {
      "word/_rels/document.xml.rels":
        '<Relationships><Relationship TargetMode="External" Type="urn:fixture/image" Target="https://example.invalid/image"/></Relationships>',
    }),
  ).toContain("EXTERNAL_CONTENT");
});
it("bounds central metadata, detects CRC corruption and rejects malformed XML", () => {
  const bytes = docxFixture(undefined, {}, false);
  const broken = Buffer.from(bytes);
  broken[50] = broken[50]! ^ 1;
  expect(inspectWordBytes(broken).issues.length).toBeGreaterThan(0);
  const bomb = Buffer.from(bytes);
  const central = bomb.indexOf(Buffer.from([0x50, 0x4b, 0x01, 0x02]));
  bomb.writeUInt32LE(101 * 1048576, central + 24);
  expect(inspectWordBytes(bomb).issues.map((x) => x.code)).toContain(
    "PACKAGE_LIMIT",
  );
  expect(codes("<w:p>")).toContain("MALFORMED_XML");
  expect(inspectWordBytes(new Uint8Array([1, 2, 3])).issues[0]?.code).toBe(
    "INVALID_DOCX",
  );
});
it("rejects duplicate, escaping and encrypted entries", () => {
  for (const name of ["../escape.xml", "/absolute.xml", "word\\unsafe.xml"])
    expect(codes("<w:p><w:t>Text</w:t></w:p>", { [name]: "<x/>" })).toContain(
      "UNSAFE_PACKAGE",
    );
  const encrypted = docxFixture();
  const central = encrypted.indexOf(Buffer.from([0x50, 0x4b, 0x01, 0x02]));
  encrypted.writeUInt16LE(0x801, central + 8);
  expect(inspectWordBytes(encrypted).issues.map((x) => x.code)).toContain(
    "UNSAFE_PACKAGE",
  );
});
