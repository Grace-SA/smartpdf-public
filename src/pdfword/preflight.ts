// Local signature check only. Full parsing happens after explicit upload.
export async function checkPdfLocally(file: File, signal: AbortSignal) {
  const signature = await file.slice(0, 5).text();
  if (signal.aborted) throw new DOMException("Cancelled", "AbortError");
  if (signature !== "%PDF-") throw Error("Choose a valid PDF file.");
}
