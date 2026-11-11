import { enabledTools, toolCatalog } from "../src/routes.ts";
import { mkdir, readFile, writeFile } from "node:fs/promises";

const origin = "https://smartpdf.com.au";
const outputDirectory = process.argv[2] || "dist";
const reviewProtect = process.env.VITE_ENABLE_PROTECT === "true";
const reviewExcel = process.env.VITE_ENABLE_EXCEL === "true";
const publicTools = enabledTools(
  reviewProtect,
  reviewExcel,
  process.env.VITE_ENABLE_PDF_EXCEL === "true",
);
const pages = {
  "powerpoint-to-pdf": {
    title: "PowerPoint to PDF – PPTX Conversion | Smart PDF",
    description:
      "Convert a PPTX with clearly marked cloud processing. Keep the original slide size, preview and download your PDF.",
    keywords: "powerpoint to pdf, pptx to pdf",
    heading: "Convert PowerPoint slides to PDF",
  },
  ...(reviewExcel
    ? {
        "excel-to-pdf": {
          title: "Excel to PDF – XLSX Worksheets | Smart PDF",
          description:
            "Convert selected visible worksheets with cloud processing. Keep print areas and check your PDF before sharing.",
          keywords: "excel to pdf, xlsx to pdf",
          heading: "Convert Excel worksheets to PDF",
        },
      }
    : {}),
  ...(process.env.VITE_ENABLE_PDF_EXCEL === "true"
    ? {
        "pdf-to-excel": {
          title: "PDF to Excel - Editable Tables | Smart PDF",
          description:
            "Extract PDF tables into editable Excel worksheets using self-hosted processing. Review table previews and preserve text, leading zeros and long numbers.",
          keywords: "pdf to excel, pdf to xlsx",
          heading: "Convert PDF tables to Excel",
        },
      }
    : {}),
  "word-to-pdf": {
    title: "Word to PDF – Cloud DOCX Conversion | Smart PDF",
    description:
      "Convert a DOCX using self-hosted cloud conversion. Upload only when you start, check your PDF and delete temporary files. Fonts and pagination may change.",
    keywords: "word to pdf, docx to pdf, cloud document conversion",
    heading: "Convert a Word document to PDF",
  },
  "protect-pdf": {
    title: "Protect PDF Free Online – AES-256, No Upload | Smart PDF",
    description:
      "Add an opening password to a PDF for free on your device. Verified AES-256 protection without uploading your PDF or password.",
    keywords:
      "free protect pdf, password protect pdf, encrypt pdf, aes-256 pdf, private pdf protection",
    heading: "Protect PDF without uploading your document or password",
  },
  "unlock-pdf": {
    title: "Unlock PDF Free Online – Remove Password, No Upload | Smart PDF",
    description:
      "Remove a known PDF password for free on your device. Download an unlocked copy without uploading your document or password.",
    keywords:
      "free unlock pdf, remove pdf password, decrypt pdf, private pdf unlock",
    heading: "Unlock PDF without uploading your document or password",
  },
  "add-page-numbers": {
    title: "Add Page Numbers to PDF Free Online – No Upload | Smart PDF",
    description:
      "Add page numbers to PDF files for free on your device. Skip a cover, choose a range, position and starting number, then download a new PDF. No upload.",
    keywords:
      "free add page numbers to pdf, number pdf pages, pdf page numbering, private pdf tools",
    heading: "Add page numbers without uploading your PDF",
  },
  "watermark-pdf": {
    title: "Watermark PDF Free Online – Text & Image, No Upload | Smart PDF",
    description:
      "Add text or image watermarks to PDF files for free on your device. Adjust position, opacity, angle and pages, then download a new PDF. No upload.",
    keywords:
      "free watermark pdf, add watermark to pdf, text watermark, image watermark, private pdf watermark",
    heading: "Add a watermark without uploading your PDF",
  },
  "pdf-to-jpg": {
    title: "PDF to JPG & PNG Free Online – No Upload | Smart PDF",
    description:
      "Convert PDF pages to JPG or PNG for free on your device. Choose pages and image quality, then download images privately. No upload.",
    keywords:
      "free pdf to jpg, free pdf to png, pdf to image, private pdf converter",
    heading: "PDF to JPG and PNG without uploading your file",
  },
  "rotate-pdf": {
    title: "Rotate PDF Pages Free Online & Privately | Smart PDF",
    description:
      "Rotate PDF pages for free on your device. Turn one page, selected pages or the whole PDF, then download a corrected copy. No upload.",
    keywords:
      "free rotate pdf, rotate pdf pages, rotate pdf online, private pdf rotation",
    heading: "Rotate PDF pages privately in your browser",
  },
  "": {
    title: "Free Private PDF Tools – No Uploads | Smart PDF",
    description:
      "Use free PDF tools to merge, split, organize, convert, sign and compress files in your browser. Files and filenames stay on your device.",
    keywords:
      "free pdf tools, free pdf merger, free pdf splitter, free pdf organizer, free images to pdf, free pdf signature, free pdf compressor, private pdf tools",
    heading: "Private PDF tools. No uploads.",
  },
  "merge-pdf": {
    title: "Merge PDF Online Free & Privately | Smart PDF",
    description:
      "Merge PDFs for free in your browser. Reorder documents, preserve supported links and bookmarks, then download one PDF. No file upload.",
    keywords:
      "free merge pdf, free pdf merger, merge pdf online, private pdf merger",
    heading: "Merge PDF files privately in your browser",
  },
  "split-pdf": {
    title: "Split PDF Online Free & Privately | Smart PDF",
    description:
      "Split PDFs for free by selected pages, ranges, every page or fixed groups. Process locally and download without uploading your file.",
    keywords:
      "free split pdf, free pdf splitter, split pdf online, split pdf pages",
    heading: "Split PDF pages into the files you need",
  },
  "organize-pdf": {
    title: "Organize PDF Pages Free Online | Smart PDF",
    description:
      "Organize PDF pages for free in your browser: reorder, rotate or delete pages, then download your copy. No upload.",
    keywords:
      "free organize pdf, free pdf organizer, organize pdf pages, reorder pdf pages",
    heading: "Reorder, rotate and remove PDF pages",
  },
  "images-to-pdf": {
    title: "Convert Images to PDF Free – JPG, PNG & HEIC | Smart PDF",
    description:
      "Convert up to 20 JPG, PNG or supported HEIC images to PDF for free. Arrange photos, choose a layout and process locally.",
    keywords:
      "free images to pdf, free jpg to pdf, free png to pdf, free heic to pdf, image to pdf converter",
    heading: "Convert JPG, PNG and HEIC images to PDF",
  },
  "sign-pdf": {
    title: "Sign PDF Free Online – Draw, Type or Upload | Smart PDF",
    description:
      "Sign PDFs for free in your browser. Draw, type your name or add a signature image; your document stays on your device.",
    keywords:
      "free sign pdf, free pdf signature, sign pdf online, add signature to pdf",
    heading: "Add your visible signature to a PDF",
  },
  "compress-pdf": {
    title: "Compress PDF Online Free & Privately | Smart PDF",
    description:
      "Compress PDFs for free with three local compression levels. Keep the original if no smaller safe result is found. No upload.",
    keywords:
      "free compress pdf, free pdf compressor, compress pdf online, reduce pdf file size",
    heading: "Compress a PDF without uploading it",
  },
};

if (!reviewProtect) delete pages["protect-pdf"];

const base = await readFile(`${outputDirectory}/index.html`, "utf8");

const replaceTag = (html, pattern, replacement, label) => {
  if (!pattern.test(html)) {
    throw new Error(`Unable to generate SEO page: ${label} was not found.`);
  }
  return html.replace(pattern, replacement);
};

for (const [slug, page] of Object.entries(pages)) {
  const path = slug ? `/${slug}/` : "/";
  const canonical = origin + path;
  const schema = JSON.stringify({
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "Smart PDF",
    applicationCategory: "BusinessApplication",
    operatingSystem: "Any",
    url: canonical,
    description: page.description,
    offers: { "@type": "Offer", price: "0", priceCurrency: "AUD" },
    featureList: [
      "Local browser PDF processing",
      ...(slug === "word-to-pdf" || slug === "powerpoint-to-pdf"
        ? ["Explicit cloud upload"]
        : ["No document upload"]),
      page.heading,
    ],
  }).replaceAll("<", "\\u003c");
  let html = base;
  html = replaceTag(
    html,
    /<title>[\s\S]*?<\/title>/,
    `<title>${page.title}</title>`,
    "title",
  );
  html = replaceTag(
    html,
    /<meta\s+name="description"\s+content="[^"]*"\s*\/?>/,
    `<meta name="description" content="${page.description}" />`,
    "description",
  );
  html = replaceTag(
    html,
    /<meta\s+name="keywords"\s+content="[^"]*"\s*\/?>/,
    `<meta name="keywords" content="${page.keywords}" />`,
    "keywords",
  );
  html = replaceTag(
    html,
    /<link\s+rel="canonical"\s+href="[^"]*"\s*\/?>/,
    `<link rel="canonical" href="${canonical}" />`,
    "canonical",
  );
  html = replaceTag(
    html,
    /<meta\s+property="og:title"\s+content="[^"]*"\s*\/?>/,
    `<meta property="og:title" content="${page.title}" />`,
    "Open Graph title",
  );
  html = replaceTag(
    html,
    /<meta\s+property="og:description"\s+content="[^"]*"\s*\/?>/,
    `<meta property="og:description" content="${page.description}" />`,
    "Open Graph description",
  );
  html = replaceTag(
    html,
    /<meta\s+property="og:url"\s+content="[^"]*"\s*\/?>/,
    `<meta property="og:url" content="${canonical}" />`,
    "Open Graph URL",
  );
  html = replaceTag(
    html,
    /<meta\s+name="twitter:title"\s+content="[^"]*"\s*\/?>/,
    `<meta name="twitter:title" content="${page.title}" />`,
    "Twitter title",
  );
  html = replaceTag(
    html,
    /<meta\s+name="twitter:description"\s+content="[^"]*"\s*\/?>/,
    `<meta name="twitter:description" content="${page.description}" />`,
    "Twitter description",
  );
  html = html
    .replace(
      "</head>",
      `    <script type="application/ld+json">${schema}</script>\n  </head>`,
    )
    .replace(
      '<div id="root"></div>',
      `<div id="root"></div><noscript><main><h1>${page.heading}</h1><p>${page.description}</p><p>Smart PDF requires JavaScript to process files locally in your browser.</p><nav>${publicTools.map((id) => `<a href="${toolCatalog[id].path}">${toolCatalog[id].title}</a>`).join(" · ")}</nav></main></noscript>`,
    );

  const requiredOutput = [
    `<title>${page.title}</title>`,
    `<meta name="description" content="${page.description}" />`,
    `<meta name="keywords" content="${page.keywords}" />`,
    `<link rel="canonical" href="${canonical}" />`,
    `<meta property="og:title" content="${page.title}" />`,
    `<meta property="og:description" content="${page.description}" />`,
    `<meta property="og:url" content="${canonical}" />`,
    `<meta name="twitter:title" content="${page.title}" />`,
    `<meta name="twitter:description" content="${page.description}" />`,
    `<h1>${page.heading}</h1>`,
    `<script type="application/ld+json">${schema}</script>`,
  ];
  for (const expected of requiredOutput) {
    if (!html.includes(expected)) {
      throw new Error(`SEO validation failed for ${path}: ${expected}`);
    }
  }
  const folder = slug ? `${outputDirectory}/${slug}` : outputDirectory;
  await mkdir(folder, { recursive: true });
  await writeFile(`${folder}/index.html`, html);
}
// Use the same catalogue as navigation and tool recommendations. A separately
// maintained public XML file can silently omit newly published tools.
const sitemapPages = [
  { path: "/", frequency: "weekly", priority: "1.0" },
  ...publicTools.map((tool) => ({
    path: toolCatalog[tool].path,
    frequency: "monthly",
    priority: "0.9",
  })),
  { path: "/privacy/", frequency: "yearly", priority: "0.3" },
];
await writeFile(
  `${outputDirectory}/sitemap.xml`,
  `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${sitemapPages
    .map(
      (page) =>
        `  <url><loc>${origin}${page.path}</loc><changefreq>${page.frequency}</changefreq><priority>${page.priority}</priority></url>`,
    )
    .join("\n")}\n</urlset>\n`,
);
console.log(`Generated ${Object.keys(pages).length} indexable SEO pages.`);
