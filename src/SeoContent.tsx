import {
  absoluteUrl,
  toolPaths,
  publicTools,
  toolCatalog,
  type PublicTool,
} from "./routes";
import { ToolIcon } from "./ToolIcon";

type SeoPage = {
  title: string;
  description: string;
  keywords: string;
  heading: string;
  intro: string;
  steps: [string, string, string];
  faq: [string, string][];
};

export const seoPages: Record<PublicTool, SeoPage> = {
  protect: {
    title: "Protect PDF Free Online – AES-256, No Upload | Smart PDF",
    description:
      "Add an opening password to a PDF for free on your device. Verified AES-256 protection without uploading your PDF or password.",
    keywords:
      "free protect pdf, password protect pdf, encrypt pdf, aes-256 pdf, private pdf protection",
    heading: "Protect PDF",
    intro: "Set an opening password, privately.",
    steps: [
      "Choose an ordinary PDF.",
      "Enter and confirm your password.",
      "Protect and download your PDF.",
    ],
    faq: [
      [
        "Are my PDF and password uploaded?",
        "No. Encryption and verification happen in your browser. Your original stays unchanged.",
      ],
      [
        "What protection is added?",
        "AES-256 opening protection. Anyone who knows the password can read, copy or print the content. No printing or copying restrictions are promised.",
      ],
      [
        "Can you recover a forgotten password?",
        "No. Keep your password safe and share it with your recipient separately.",
      ],
      [
        "Which PDFs are supported?",
        "One ordinary, unencrypted PDF up to 30 MiB and 200 pages, within the resource limits. Existing encryption, digital signatures, Content Credentials, conformance declarations and unsupported structures are refused.",
      ],
    ],
  },
  unlock: {
    title: "Unlock PDF Free Online – Remove Password, No Upload | Smart PDF",
    description:
      "Remove a known PDF password for free on your device. Download an unlocked copy without uploading your document or password.",
    keywords:
      "free unlock pdf, remove pdf password, decrypt pdf, private pdf unlock",
    heading: "Unlock PDF",
    intro: "Remove a known password, privately.",
    steps: [
      "Choose a protected PDF.",
      "Enter its password if needed.",
      "Unlock and download a copy.",
    ],
    faq: [
      [
        "Are my PDF and password uploaded?",
        "No. Both stay on this device; unlocking happens in your browser.",
      ],
      [
        "Can this recover a forgotten password?",
        "No. A valid opening or owner password is needed unless the PDF can already be accessed without one. Only unlock files you own or have permission to change.",
      ],
      [
        "Will the new PDF ask for a password?",
        "A verified unlocked copy opens without the removed password. Your original stays unchanged. Digital signatures and unsupported protection methods are refused.",
      ],
    ],
  },
  numbers: {
    title: "Add Page Numbers to PDF Free Online – No Upload | Smart PDF",
    description:
      "Add page numbers to PDF files for free on your device. Skip a cover, choose a range, position and starting number, then download a new PDF. No upload.",
    keywords:
      "free add page numbers to pdf, number pdf pages, pdf page numbering, private pdf tools",
    heading: "Add page numbers",
    intro: "Number your pages, privately.",
    steps: [
      "Choose a PDF.",
      "Choose the numbering and position.",
      "Download a new PDF.",
    ],
    faq: [
      [
        "Can I skip the cover page?",
        "Yes. Choose Skip first page; your cover stays in the PDF and numbering starts on the next page.",
      ],
      [
        "Will this replace existing page numbers?",
        "No. It adds visible numbers in the position you choose. Existing numbers and PDF page labels are unchanged; check the preview for a clear position.",
      ],
      [
        "What does the total mean?",
        "The total is the last printed number. For example, five numbered pages starting at 3 show 3 / 7 through 7 / 7. Files are processed on your device without upload.",
      ],
    ],
  },
  watermark: {
    title: "Watermark PDF Free Online – Text & Image, No Upload | Smart PDF",
    description:
      "Add text or image watermarks to PDF files for free on your device. Adjust position, opacity, angle and pages, then download a new PDF. No upload.",
    keywords:
      "free watermark pdf, add watermark to pdf, text watermark, image watermark, private pdf watermark",
    heading: "Watermark PDF",
    intro: "Add a visible label or logo, privately.",
    steps: [
      "Choose a PDF.",
      "Set your text or image watermark.",
      "Download a new PDF.",
    ],
    faq: [
      [
        "Are my PDF and watermark uploaded?",
        "No. Your PDF, watermark text and image stay on this device.",
      ],
      [
        "Does a watermark prevent copying?",
        "No. A watermark is a visible label. It does not prevent copying, screenshots or removal, and it does not replace a certificate signature.",
      ],
    ],
  },
  raster: {
    title: "PDF to JPG & PNG Free Online – No Upload | Smart PDF",
    description:
      "Convert PDF pages to JPG or PNG for free on your device. Choose pages and image quality, then download images privately. No upload.",
    keywords:
      "free pdf to jpg, free pdf to png, pdf to image, private pdf converter",
    heading: "PDF to JPG / PNG",
    intro: "Save your PDF pages as images, privately.",
    steps: [
      "Choose a PDF.",
      "Choose pages, format and quality.",
      "Download your images.",
    ],
    faq: [
      [
        "Are my files uploaded?",
        "No. PDF pages are converted on your device. Your original PDF is unchanged.",
      ],
      [
        "What is the difference between JPG and PNG?",
        "JPG usually creates smaller files. PNG preserves sharp text without lossy image encoding. Both use a white page background.",
      ],
    ],
  },
  rotate: {
    title: "Rotate PDF Pages Free Online & Privately | Smart PDF",
    description:
      "Rotate PDF pages for free on your device. Turn one page, selected pages or the whole PDF, then download a corrected copy. No upload.",
    keywords:
      "free rotate pdf, rotate pdf pages, rotate pdf online, private pdf rotation",
    heading: "Rotate PDF pages",
    intro: "Turn your pages the right way, then download a new PDF.",
    steps: [
      "Choose a PDF.",
      "Rotate one page or all pages.",
      "Create and download your PDF.",
    ],
    faq: [
      [
        "Can I rotate only some pages?",
        "Yes. Turn a single page using its rotation button, or choose Selected pages for batch rotation.",
      ],
      [
        "Does rotation reduce PDF quality?",
        "No. Rotation changes page orientation without turning text or vectors into images. Your original is unchanged.",
      ],
    ],
  },
  combine: {
    title: "Merge PDF Online Free & Privately | Smart PDF",
    description:
      "Merge PDFs for free in your browser. Reorder documents, preserve supported links and bookmarks, then download one PDF. No file upload.",
    keywords:
      "free merge pdf, free pdf merger, merge pdf online, private pdf merger",
    heading: "How to merge PDFs",
    intro: "Choose your files, set the order and download one PDF.",
    steps: [
      "Choose two to ten PDFs.",
      "Drag them into order.",
      "Merge and download your PDF.",
    ],
    faq: [
      [
        "Are my PDFs uploaded?",
        "No. Supported PDFs are processed in your browser and are not uploaded by Smart PDF.",
      ],
      [
        "Can I change the order?",
        "Yes. Reorder the selected files before creating the merged PDF.",
      ],
    ],
  },
  split: {
    title: "Split PDF Online Free & Privately | Smart PDF",
    description:
      "Split PDFs for free by selected pages, ranges, every page or fixed groups. Process locally and download without uploading your file.",
    keywords:
      "free split pdf, free pdf splitter, split pdf online, split pdf pages",
    heading: "How to split a PDF",
    intro: "Choose pages or ranges and download the new files.",
    steps: [
      "Choose one PDF.",
      "Select pages or define ranges.",
      "Split and download one PDF or a ZIP.",
    ],
    faq: [
      [
        "Can I split a PDF into several files?",
        "Yes. Use page ranges, fixed groups or one file per selected page.",
      ],
      [
        "Does splitting change my original?",
        "No. Smart PDF creates new files and leaves the original unchanged.",
      ],
    ],
  },
  organize: {
    title: "Organize PDF Pages Free Online | Smart PDF",
    description:
      "Organize PDF pages for free in your browser: reorder, rotate or delete pages, then download your copy. No upload.",
    keywords:
      "free organize pdf, free pdf organizer, organize pdf pages, reorder pdf pages",
    heading: "How to organize PDF pages",
    intro: "Reorder, rotate or remove pages, then download a new copy.",
    steps: [
      "Choose one PDF.",
      "Move, rotate or remove pages.",
      "Apply changes and download the new PDF.",
    ],
    faq: [
      [
        "Can I undo page changes?",
        "Yes. Undo and redo are available while you are organizing the current PDF.",
      ],
      [
        "What happens to links and bookmarks?",
        "Supported structure is preserved. Smart PDF explains when a change cannot be made safely.",
      ],
    ],
  },
  photos: {
    title: "Convert Images to PDF Free – JPG, PNG & HEIC | Smart PDF",
    description:
      "Convert up to 20 JPG, PNG or supported HEIC images to PDF for free. Arrange photos, choose a layout and process locally.",
    keywords:
      "free images to pdf, free jpg to pdf, free png to pdf, free heic to pdf, image to pdf converter",
    heading: "How to convert images to PDF",
    intro: "Arrange JPG, PNG or supported HEIC images and create one PDF.",
    steps: [
      "Choose up to 20 images.",
      "Arrange and rotate your photos.",
      "Choose the layout, convert and download.",
    ],
    faq: [
      [
        "Which images are supported?",
        "Smart PDF accepts JPEG, PNG and supported HEIC still images within the displayed limits.",
      ],
      [
        "Can I control the page layout?",
        "Yes. Choose paper size and orientation before creating the PDF.",
      ],
    ],
  },
  sign: {
    title: "Sign PDF Free Online – Draw, Type or Upload | Smart PDF",
    description:
      "Sign PDFs for free in your browser. Draw, type your name or add a signature image; your document stays on your device.",
    keywords:
      "free sign pdf, free pdf signature, sign pdf online, add signature to pdf",
    heading: "How to sign a PDF",
    intro: "Create a signature, place it on the page and download a new PDF.",
    steps: [
      "Choose one PDF.",
      "Draw, type or add your signature image.",
      "Place it, create the signed copy and download.",
    ],
    faq: [
      [
        "Is this a certificate digital signature?",
        "No. This tool adds a visible electronic signature and does not issue an identity certificate.",
      ],
      [
        "Can I sign more than one page?",
        "Yes. Place supported signature assets on the pages you choose.",
      ],
    ],
  },
  compress: {
    title: "Compress PDF Online Free & Privately | Smart PDF",
    description:
      "Compress PDFs for free with three local compression levels. Keep the original if no smaller safe result is found. No upload.",
    keywords:
      "free compress pdf, free pdf compressor, compress pdf online, reduce pdf file size",
    heading: "How to compress a PDF",
    intro:
      "Choose a quality level and download a smaller PDF when safe compression is possible.",
    steps: [
      "Choose one PDF.",
      "Select a compression level.",
      "Compress, compare the result and download.",
    ],
    faq: [
      [
        "Will every PDF become smaller?",
        "No. A PDF that is already optimized may stay the same size; Smart PDF keeps the original bytes when no smaller safe result is found.",
      ],
      [
        "Does compression rasterize every page?",
        "No. Smart PDF preserves text and vectors and only recompresses supported image structures.",
      ],
    ],
  },
};

export const homeSeo = {
  title: "Free Private PDF Tools – No Uploads | Smart PDF",
  description:
    "Use free PDF tools to merge, split, organize, convert, sign and compress files in your browser. Files and filenames stay on your device.",
  keywords:
    "free pdf tools, free pdf merger, free pdf splitter, free pdf organizer, free images to pdf, free pdf signature, free pdf compressor, private pdf tools",
};

export function applySeo(tool: PublicTool | null) {
  const page = tool ? seoPages[tool] : homeSeo;
  const path = tool ? toolPaths[tool] : "/";
  document.title = page.title;
  const set = (selector: string, attribute: string, value: string) =>
    document.querySelector(selector)?.setAttribute(attribute, value);
  set('meta[name="description"]', "content", page.description);
  set('meta[name="keywords"]', "content", page.keywords);
  set('meta[property="og:title"]', "content", page.title);
  set('meta[property="og:description"]', "content", page.description);
  set('meta[property="og:url"]', "content", absoluteUrl(path));
  set('meta[name="twitter:title"]', "content", page.title);
  set('meta[name="twitter:description"]', "content", page.description);
  set('link[rel="canonical"]', "href", absoluteUrl(path));
}

export function SeoContent({ tool }: { tool: PublicTool | null }) {
  if (!tool) return null;
  const page = seoPages[tool];
  return (
    <div className="upload-support">
      <section className="tool-faq" aria-labelledby="frequently-asked">
        <h2 id="frequently-asked">Frequently asked questions</h2>
        {page.faq.map(([question, answer]) => (
          <details key={question}>
            <summary>{question}</summary>
            <p>{answer}</p>
          </details>
        ))}
      </section>
      <nav className="more-tools" aria-label="More PDF tools">
        <h2>More PDF tools</h2>
        <div className="more-tools-grid">
          {publicTools
            .filter((id) => id !== tool)
            .map((id) => (
              <a href={toolPaths[id]} key={id}>
                <span className={`tool-icon icon-${id}`} aria-hidden="true">
                  <ToolIcon tool={id} />
                </span>
                <h3>{toolCatalog[id].title}</h3>
                <p>{toolCatalog[id].summary}</p>
              </a>
            ))}
        </div>
      </nav>
    </div>
  );
}
