import { glyphShape } from "../overlay/text";
let pending: Promise<Uint8Array> | null = null;
export function prepareNumberFont(signal: AbortSignal) {
  if (!pending)
    pending = fetch("/number-fonts/SmartPDFNumberSans-Regular.ttf", { signal })
      .then(async (response) => {
        if (!response.ok)
          throw Error("The page number font could not load. Retry preview.");
        const bytes = new Uint8Array(await response.arrayBuffer());
        if (bytes.byteLength > 64 * 1024)
          throw Error("The page number font exceeds its budget.");
        // A 200 response can still contain a damaged font or fallback HTML.
        // Validate before caching, so the normal retry can fetch a clean copy.
        glyphShape(bytes, "0123456789Pageof /");
        return bytes;
      })
      .catch((error) => {
        pending = null;
        throw error;
      });
  return pending;
}
