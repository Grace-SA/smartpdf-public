import { LIMITS } from "../core/contracts";
import { UnlockFailure } from "./model";
export function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}
export function auditObjects(json: unknown): Record<string, unknown> {
  if (!record(json) || !Array.isArray(json.qpdf) || !record(json.qpdf[1]))
    throw new UnlockFailure("validation");
  if (Object.keys(json.qpdf[1]).length > LIMITS.objects + 1)
    throw new UnlockFailure("resource");
  return json.qpdf[1];
}
export function auditTrailer(json: unknown): Record<string, unknown> {
  const trailer = auditObjects(json).trailer;
  if (!record(trailer) || !record(trailer.value) || !trailer.value["/Root"])
    throw new UnlockFailure("validation");
  return trailer.value;
}
/** Compare reachable logical objects, preserving cycles and shared references.
 * Transport objects, IDs and the encryption dictionary are not document content. */
export function canonicalGraph(json: unknown): string {
  const objects = auditObjects(json),
    trailer = auditTrailer(json);
  for (const object of Object.values(objects)) {
    const d = record(object)
      ? record(object.stream)
        ? object.stream.dict
        : object.value
      : null;
    if (
      record(d) &&
      ("/ByteRange" in d ||
        "/DocMDP" in d ||
        d["/FT"] === "/Sig" ||
        ["/Sig", "/DocTimeStamp"].includes(String(d["/Type"])) ||
        d["/AFRelationship"] === "/C2PA_Manifest")
    )
      throw new UnlockFailure("signature");
  }
  const ids = new Map<string, number>(),
    nodes: unknown[] = [];
  let visited = 0;
  function walk(value: unknown, depth = 0): unknown {
    if (depth > LIMITS.depth || ++visited > LIMITS.nodes)
      throw new UnlockFailure("resource");
    if (typeof value === "string" && /^\d+ \d+ R$/.test(value)) {
      if (ids.has(value)) return { $ref: ids.get(value) };
      const object = objects["obj:" + value];
      if (!object) throw new UnlockFailure("validation");
      if (ids.size >= LIMITS.objects) throw new UnlockFailure("resource");
      const id = ids.size;
      ids.set(value, id);
      nodes.push(null);
      nodes[id] = walk(object, depth + 1);
      return { $ref: id };
    }
    if (Array.isArray(value)) return value.map((v) => walk(v, depth + 1));
    if (record(value))
      return Object.fromEntries(
        Object.keys(value)
          .sort()
          .map((k) => [k, walk(value[k], depth + 1)]),
      );
    return value;
  }
  const root = walk({
    "/Root": trailer["/Root"],
    ...("/Info" in trailer ? { "/Info": trailer["/Info"] } : {}),
  });
  return JSON.stringify({ root, nodes });
}
