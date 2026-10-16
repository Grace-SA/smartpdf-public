import { XMLParser } from "fast-xml-parser";

export const standardNamespaces = new Set([
  "http://www.aiim.org/pdfa/ns/id/",
  "http://www.npes.org/pdfx/ns/id/",
  "http://www.aiim.org/pdfua/ns/id/",
]);

// A schema description, unused namespace or ordinary text mentioning PDF/A
// does not assert compliance. Match actual qualified element/attribute names.
// Caller validates XML and rejects entities before invoking this function.
export function hasStandardDeclaration(xml: string): boolean {
  type Node = Record<string, unknown>;
  const tree = new XMLParser({
    preserveOrder: true,
    ignoreAttributes: false,
    processEntities: false,
  }).parse(xml) as Node[];
  function visit(nodes: Node[], inherited: Record<string, string>): boolean {
    return nodes.some((node) => {
      const attrs = (node[":@"] ?? {}) as Record<string, string>;
      const scope = { ...inherited };
      for (const [key, value] of Object.entries(attrs)) {
        if (key === "@_xmlns") scope[""] = value;
        else if (key.startsWith("@_xmlns:")) scope[key.slice(8)] = value;
      }
      function standard(name: string, attribute = false) {
        if (/^[#?!]/.test(name)) return false;
        const parts = name.split(":");
        const prefix = parts.length > 1 ? parts[0]! : "";
        if (attribute && !prefix) return false;
        return (
          standardNamespaces.has(scope[prefix] ?? "") ||
          (!(prefix in scope) &&
            ["pdfaid", "pdfxid", "pdfuaid"].includes(prefix))
        );
      }
      const tag = Object.keys(node).find((key) => key !== ":@")!;
      if (standard(tag)) return true;
      for (const key of Object.keys(attrs)) {
        if (!key.startsWith("@_xmlns") && standard(key.slice(2), true))
          return true;
      }
      return Array.isArray(node[tag]) && visit(node[tag] as Node[], scope);
    });
  }
  return visit(tree, {});
}
