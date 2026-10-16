import { prepareOrganize } from "../organize/generate";
import { LIMITS } from "../core/contracts";
import { SPLIT_LIMIT } from "./model";
export async function splitPdf(
  bytes: Uint8Array,
  groups: number[][],
  adjust: boolean,
  budget: number,
  progress: (done: number) => void,
) {
  const checked = await prepareOrganize(bytes);
  if (
    !groups.length ||
    groups.length > SPLIT_LIMIT ||
    !Number.isFinite(budget) ||
    budget <= 0
  )
    throw new Error("Too many results or insufficient session capacity.");
  const seen = new Set<number>();
  for (const group of groups) {
    if (!group.length) throw new Error("Empty split groups are not allowed.");
    for (const [i, page] of group.entries()) {
      if (
        !Number.isInteger(page) ||
        page < 0 ||
        page >= checked.pages ||
        seen.has(page) ||
        (i > 0 && page <= group[i - 1]!)
      )
        throw new Error("Invalid or overlapping split groups.");
      seen.add(page);
    }
  }
  const outputs: Uint8Array[] = [];
  let size = 0;
  for (const [index, group] of groups.entries()) {
    const output = await checked.create(
      group.map((source) => ({ id: `source-${source}`, source, turns: 0 })),
      adjust,
    );
    size += output.length;
    if (output.length > LIMITS.bytes || size > budget)
      throw new Error(
        "Split results exceed the session capacity. Use fewer groups or a smaller PDF. No results were published.",
      );
    outputs.push(output);
    progress(index + 1);
  }
  return outputs;
}
