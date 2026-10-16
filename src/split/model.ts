import { safeFilename } from "../photos/model";
export const SPLIT_LIMIT = 50;
export function splitGroups(
  value: string,
  pages: number,
  each = false,
): number[][] {
  if (!Number.isInteger(pages) || pages < 1 || pages > 200)
    throw new Error("Use a PDF with 1–200 pages.");
  if (each) {
    if (pages > SPLIT_LIMIT)
      throw new Error(
        "Each-page mode allows at most 50 results. Use page groups instead.",
      );
    return Array.from({ length: pages }, (_, i) => [i]);
  }
  const lines = value.trim().split(/\r?\n/);
  if (!value.trim() || value.length > 10000 || lines.length > SPLIT_LIMIT)
    throw new Error("Enter 1–50 groups, one group per line.");
  const used = new Set<number>();
  return lines.map((line, index) => {
    const group: number[] = [];
    for (const token of line.replaceAll("，", ",").split(",")) {
      const match = /^\s*(\d+)\s*(?:[-–]\s*(\d+)\s*)?$/.exec(token);
      if (!match)
        throw new Error(
          `Group ${index + 1}: use page numbers such as 1-3,5. Empty groups are not allowed.`,
        );
      const first = Number(match[1]),
        last = Number(match[2] ?? match[1]);
      if (
        !Number.isSafeInteger(first) ||
        !Number.isSafeInteger(last) ||
        first < 1 ||
        last > pages ||
        first > last
      )
        throw new Error(
          `Group ${index + 1}: use ascending ranges within 1–${pages}.`,
        );
      for (let n = first; n <= last; n++) {
        if (used.has(n))
          throw new Error(
            `Page ${n} appears more than once. Groups must not overlap.`,
          );
        used.add(n);
        group.push(n - 1);
      }
    }
    return group.sort((a, b) => a - b);
  });
}
export function partNames(
  source: string,
  count: number,
  existing: string[],
): string[] {
  const used = new Set(existing.map((s) => s.toLocaleLowerCase()));
  return Array.from({ length: count }, (_, i) => {
    const stem = source.replace(/\.pdf$/i, "").slice(0, 110) || "Document";
    const base = `${stem}-part-${String(i + 1).padStart(2, "0")}`;
    let name = safeFilename(base),
      suffix = 2;
    while (used.has(name.toLocaleLowerCase()))
      name = safeFilename(`${base}-${suffix++}`);
    used.add(name.toLocaleLowerCase());
    return name;
  });
}
