import inventory from "../../config/word-font-families.stirling-3.2.2.json";
const installed = new Set(inventory.families.map((name) => name.toLowerCase()));
export function substitutedFontDeclarations(fonts: string[]) {
  return fonts.filter((name) => !installed.has(name.toLowerCase()));
}
