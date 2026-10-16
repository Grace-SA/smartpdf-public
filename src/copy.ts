import type { Reason } from "./core/contracts";
export const reasons: Record<Reason, string> = {
  encrypted: "This PDF is encrypted, even if it opens without a password.",
  signature:
    "This PDF contains certificate-signature structures. Use an unsigned original; changing it cannot preserve its certificate validity.",
  form: "This PDF contains form structures that cannot yet be preserved. This includes some files with empty form fields.",
  annotations:
    "This PDF contains an annotation structure we cannot yet preserve. Common comments, highlights and links are supported.",
  attachments: "This PDF contains attachments or a portfolio.",
  actions: "This PDF contains actions or scripts.",
  layers: "This PDF contains optional content layers.",
  navigation:
    "This PDF contains bookmarks, page labels or internal navigation.",
  tagged: "This PDF contains accessibility tags or marked structure.",
  standard: "This PDF declares a special document standard or output profile.",
  multimedia: "This PDF contains multimedia content.",
  malformed: "We could not confirm that this is a complete, supported PDF.",
  missingReference:
    "This PDF refers to an object we could not read. Try a fresh copy from its source. Your original file has not changed.",
  size: "Choose a non-empty PDF no larger than 30 MiB.",
  pages: "Choose a PDF with 1–200 pages.",
  complexity: "This PDF is too complex for this preview.",
  geometry: "This PDF contains a page larger than the preview limit.",
  image:
    "This PDF exceeds the image budget: 24 MP for JPEG, 16 MP for other images, or 32 MiB for decoded-image buffers.",
  inlineImage:
    "This PDF contains an inline image encoding this preview cannot safely check yet.",
};
export const copy = {
  privacy:
    "Your files stay in this browser. They are not uploaded or saved by this website.",
  unsupported:
    "Try an ordinary static PDF. Your original file has not changed.",
};
