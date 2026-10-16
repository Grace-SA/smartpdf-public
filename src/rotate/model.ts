export function turnPages(
  turns: number[],
  positions: number[],
  direction: -1 | 1,
) {
  if (
    ![-1, 1].includes(direction) ||
    turns.some((turn) => !Number.isInteger(turn) || turn < 0 || turn > 3) ||
    positions.some(
      (index) => !Number.isInteger(index) || index < 0 || index >= turns.length,
    )
  )
    throw new Error("Choose valid pages and a 90° rotation.");
  const selected = new Set(positions);
  return turns.map((turn, index) =>
    selected.has(index) ? (turn + direction + 4) % 4 : turn,
  );
}
