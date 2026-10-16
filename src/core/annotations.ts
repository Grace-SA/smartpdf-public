// Passive page annotations. Widgets, media and file attachments stay outside
// this contract. Actions are checked separately by the document probe.
export const passiveAnnotations = new Set([
  "Link",
  "Text",
  "FreeText",
  "Line",
  "Square",
  "Circle",
  "Polygon",
  "PolyLine",
  "Highlight",
  "Underline",
  "Squiggly",
  "StrikeOut",
  "Stamp",
  "Caret",
  "Ink",
  "Popup",
]);
