export type PageEntry = { id: string; source: number; turns: number };
export function movePages(
  pages: PageEntry[],
  selected: Set<string>,
  direction: -1 | 1,
) {
  const next = [...pages];
  const indices = pages.map((_, i) => i);
  if (direction === 1) indices.reverse();
  for (const i of indices) {
    const j = i + direction;
    if (
      j >= 0 &&
      j < next.length &&
      selected.has(next[i]!.id) &&
      !selected.has(next[j]!.id)
    )
      [next[i], next[j]] = [next[j]!, next[i]!];
  }
  return next;
}
export function placePages(
  pages: PageEntry[],
  selected: Set<string>,
  position: number,
) {
  const chosen = pages.filter((p) => selected.has(p.id));
  const rest = pages.filter((p) => !selected.has(p.id));
  rest.splice(Math.max(0, Math.min(rest.length, position)), 0, ...chosen);
  return rest;
}
