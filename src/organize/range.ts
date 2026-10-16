export function pageRange(value: string, count: number): number[] {
  const tokens = value.trim().replaceAll("，", ",").split(",");
  if (!value.trim() || value.length > 2000)
    throw new Error("Enter page positions, for example 3-8, 12.");
  const selected = new Set<number>();
  for (const token of tokens) {
    const match = /^\s*(\d+)\s*(?:[-–]\s*(\d+)\s*)?$/.exec(token);
    if (!match)
      throw new Error(
        "Use page positions such as 3-8, 12. Your selection is unchanged.",
      );
    const first = Number(match[1]),
      last = Number(match[2] ?? match[1]);
    if (
      !Number.isSafeInteger(first) ||
      !Number.isSafeInteger(last) ||
      first < 1 ||
      last > count ||
      first > last
    )
      throw new Error(
        `Choose positions from 1 to ${count}, with ranges in ascending order. Your selection is unchanged.`,
      );
    for (let n = first; n <= last; n++) selected.add(n - 1);
  }
  return [...selected].sort((a, b) => a - b);
}
