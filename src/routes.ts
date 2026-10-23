export const toolGroups = [
  "Organize PDF",
  "Convert PDF",
  "Optimize PDF",
  "Sign & mark",
  "PDF security",
] as const;

// All public tool discovery surfaces share this catalogue.
export const toolCatalog = {
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
} as const;

export type PublicTool = keyof typeof toolCatalog;
export const publicTools = Object.keys(toolCatalog) as PublicTool[];
export const shortcutTools: PublicTool[] = ["combine", "split", "compress"];
export const toolPaths = Object.fromEntries(
  publicTools.map((id) => [id, toolCatalog[id].path]),
) as Record<PublicTool, string>;

export function toolFromPath(pathname: string): PublicTool | null {
  const normalized = pathname.endsWith("/") ? pathname : pathname + "/";
  return publicTools.find((id) => toolPaths[id] === normalized) ?? null;
}
export const absoluteUrl = (path = "/") => `https://smartpdf.com.au${path}`;
