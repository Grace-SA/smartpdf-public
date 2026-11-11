export const MAX_PDF_BYTES = 30 * 1024 * 1024;
export function validatePdf(file: Pick<File, "name" | "size">): string {
  if (!/\.pdf$/i.test(file.name)) return "Choose a PDF file.";
  if (!file.size) return "This file is empty. Choose another PDF.";
  if (file.size > MAX_PDF_BYTES) return "Choose a PDF up to 30 MiB.";
  return "";
}
export function validPages(value: string): boolean {
  if (!value.trim() || value.trim().toLowerCase() === "all") return true;
  return (
    value.length <= 1000 &&
    value.split(",").every((part) => {
      const match = /^\s*([1-9]\d*)(?:\s*-\s*([1-9]\d*))?\s*$/.exec(part);
      return (
        !!match &&
        Number(match[1]) <= Number(match[2] || match[1]) &&
        Number(match[2] || match[1]) <= 200
      );
    })
  );
}
export function outputName(name: string): string {
  return (
    (name
      .replace(/\.pdf$/i, "")
      .replace(/[\\/:*?"<>|]/g, "_")
      .split("")
      .map((char) => (char.charCodeAt(0) < 32 ? "_" : char))
      .join("")
      .slice(0, 160) || "converted") + ".xlsx"
  );
}
