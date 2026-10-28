import { test, expect } from "vitest";
import {
  classifyAccess,
  validatePassword,
  UnlockFailure,
} from "../src/unlock/model";
import { legacyPasswordHex } from "../src/unlock/engine";
import { canonicalGraph } from "../src/unlock/audit";

test("locked WASM access codes never confuse a wrong password with unencrypted input", () => {
  expect(classifyAccess(2, "")).toBe("not-encrypted");
  expect(classifyAccess(3, "")).toBe("accessible");
  expect(classifyAccess(2, "program: /input.pdf: invalid password\n")).toBe(
    "password-required",
  );
  expect(() => classifyAccess(2, "unsupported encryption filter")).toThrow(
    UnlockFailure,
  );
  expect(() => classifyAccess(2, "damaged PDF")).toThrow("invalid");
  expect(() => classifyAccess(3, "repaired xref")).toThrow("invalid");
});
test("passwords preserve spaces, punctuation and Unicode without truncation", () => {
  for (const password of [
    "",
    "  password  ",
    "='quote\"",
    "合成✓",
    "😀",
    "a".repeat(127),
  ])
    expect(() => validatePassword(password)).not.toThrow();
  for (const password of ["a".repeat(128), "bad\u0000", "a\nb", "\ud800"])
    expect(() => validatePassword(password)).toThrow("password-format");
  expect(legacyPasswordHex("é space")).toBe("e9207370616365");
  expect(legacyPasswordHex("合成✓")).toBe(null);
  expect(legacyPasswordHex("ascii")).toBe(null);
});
function graph(a = 1, b = 2, text = "u:kept") {
  return {
    qpdf: [
      {},
      {
        trailer: {
          value: { "/Root": `${a} 0 R`, "/Encrypt": "9 0 R", "/ID": ["b:11"] },
        },
        [`obj:${a} 0 R`]: { value: { "/Next": `${b} 0 R` } },
        [`obj:${b} 0 R`]: { value: { "/Parent": `${a} 0 R`, "/Text": text } },
      },
    ],
  };
}
test("logical audits preserve cycles/content while accepting object renumbering", () => {
  expect(canonicalGraph(graph(1, 2))).toBe(canonicalGraph(graph(7, 8)));
  expect(canonicalGraph(graph(1, 2))).not.toBe(
    canonicalGraph(graph(1, 2, "u:lost")),
  );
  expect(() =>
    canonicalGraph({
      qpdf: [{}, { trailer: { value: { "/Root": "99 0 R" } } }],
    }),
  ).toThrow("validation");
  expect(() =>
    canonicalGraph({
      qpdf: [
        {},
        {
          trailer: { value: { "/Root": "1 0 R" } },
          "obj:1 0 R": { value: { "/ByteRange": [0, 1, 2, 3] } },
        },
      ],
    }),
  ).toThrow("signature");
});
