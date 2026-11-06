export const toolGroups = [
  "Organize PDF",
  "Convert PDF",
  "Optimize PDF",
  "Sign & mark",
  "PDF security",
] as const;

// All public tool discovery surfaces share this catalogue.
export const toolCatalog = {
  ppt: {
    path: "/powerpoint-to-pdf/",
    title: "PowerPoint to PDF",
    label: "PowerPoint to PDF",
    summary:
      "Convert a PPTX with cloud processing. Keep the original slide size.",
    group: "Convert PDF",
  },
  excel: {
    path: "/excel-to-pdf/",
    title: "Excel to PDF",
    label: "Excel to PDF",
    summary: "Choose worksheets and convert an XLSX with cloud processing.",
    group: "Convert PDF",
  },
  word: {
    path: "/word-to-pdf/",
    title: "Word to PDF",
    label: "Word to PDF",
    summary: "Convert a DOCX with cloud processing. Preview before sharing.",
    group: "Convert PDF",
  },
  combine: {
    path: "/merge-pdf/",
    title: "Merge PDF",
    label: "Combine PDFs",
    summary: "Combine PDFs in the order you choose.",
    group: "Organize PDF",
  },
  split: {
    path: "/split-pdf/",
    title: "Split PDF",
    label: "Split a PDF",
    summary: "Separate pages into the files you need.",
    group: "Organize PDF",
  },
  organize: {
    path: "/organize-pdf/",
    title: "Organize PDF",
    label: "Organize pages",
    summary: "Reorder, rotate and remove PDF pages.",
    group: "Organize PDF",
  },
  photos: {
    path: "/images-to-pdf/",
    title: "Images to PDF",
    label: "Turn Photos into PDF",
    summary: "Turn up to 20 photos into one PDF.",
    group: "Convert PDF",
  },
  sign: {
    path: "/sign-pdf/",
    title: "Sign PDF",
    label: "Sign PDF",
    summary: "Draw, type or add an image signature.",
    group: "Sign & mark",
  },
  compress: {
    path: "/compress-pdf/",
    title: "Compress PDF",
    label: "Compress PDF",
    summary: "Reduce file size while preserving common structure.",
    group: "Optimize PDF",
  },
  rotate: {
    path: "/rotate-pdf/",
    title: "Rotate PDF",
    label: "Rotate PDF",
    summary: "Turn one page or your whole PDF the right way.",
    group: "Organize PDF",
  },
  raster: {
    path: "/pdf-to-jpg/",
    title: "PDF to JPG / PNG",
    label: "PDF to JPG / PNG",
    summary: "Save PDF pages as JPG or PNG images.",
    group: "Convert PDF",
  },
  watermark: {
    path: "/watermark-pdf/",
    title: "Watermark PDF",
    label: "Watermark PDF",
    summary: "Add a text or image watermark privately.",
    group: "Sign & mark",
  },
  numbers: {
    path: "/add-page-numbers/",
    title: "Page Numbers",
    label: "Add page numbers",
    summary: "Number PDF pages, with an optional cover page.",
    group: "Sign & mark",
  },
  unlock: {
    path: "/unlock-pdf/",
    title: "Unlock PDF",
    label: "Unlock PDF",
    summary: "Remove a known password on your device.",
    group: "PDF security",
  },
  protect: {
    path: "/protect-pdf/",
    title: "Protect PDF",
    label: "Protect PDF",
    summary: "Add an opening password on your device.",
    group: "PDF security",
  },
} as const;

export type PublicTool = keyof typeof toolCatalog;
export const publicTools = Object.keys(toolCatalog) as PublicTool[];
// Protect source remains reviewable while its separate release acceptance is pending.
export const enabledTools = (
  includeProtect = false,
  includeExcel = false,
): PublicTool[] =>
  publicTools.filter(
    (tool) =>
      (includeProtect || tool !== "protect") &&
      (includeExcel || tool !== "excel"),
  );
export const shortcutTools: PublicTool[] = ["combine", "split", "compress"];
export const toolPaths = Object.fromEntries(
  publicTools.map((id) => [id, toolCatalog[id].path]),
) as Record<PublicTool, string>;

export function toolFromPath(
  pathname: string,
  tools: readonly PublicTool[] = publicTools,
): PublicTool | null {
  const normalized = pathname.endsWith("/") ? pathname : pathname + "/";
  return tools.find((id) => toolPaths[id] === normalized) ?? null;
}
export const absoluteUrl = (path = "/") => `https://smartpdf.com.au${path}`;
