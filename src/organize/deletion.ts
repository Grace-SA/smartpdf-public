import {
  PDFArray,
  PDFDict,
  PDFDocument,
  PDFName,
  PDFNumber,
  PDFObject,
  PDFString,
  PDFHexString,
} from "pdf-lib";
import { inspectNavigation } from "../combine/navigation";
import { inspectTags } from "../combine/tags";
const k = PDFName.of;
/** Explicit opt-in only: trim associations belonging to intentionally removed pages.
 * Keep visible links/bookmark titles, but remove destinations to absent pages.
 * Legacy index/parent relationships are retained; unlocated content is not pruned.
 */
export function trimDeletedAssociations(doc: PDFDocument, kept: Set<number>) {
  const pages = doc.getPages(),
    nav = inspectNavigation(doc),
    tags = inspectTags(doc);
  const removedTags = new Set<PDFDict>();
  const resolve = (v: PDFObject | undefined) =>
    v ? doc.context.lookup(v) : undefined;
  function entries(
    raw: PDFObject | undefined,
    key: "Nums" | "Names",
  ): PDFObject[] {
    const d = resolve(raw);
    if (!(d instanceof PDFDict)) return [];
    const list = resolve(d.get(k(key)));
    if (list instanceof PDFArray) return list.asArray();
    const kids = resolve(d.get(k("Kids")));
    return kids instanceof PDFArray
      ? kids.asArray().flatMap((v) => entries(v, key))
      : [];
  }
  // Unknown ownership stays unknown and is retained in every result. Only
  // content explicitly owned by a removed page is pruned; do not invent /Pg.
  if (tags) {
    type Node = (typeof tags.children)[number];
    const memo = new Map<Node, boolean>();
    function retain(node: Node): boolean {
      const cached = memo.get(node);
      if (cached !== undefined) return cached;
      // Keep indirect identity shared with ParentTree/IDTree. Inlining a single
      // referenced child creates a second structure element when serialized.
      const reference = node.source.get(k("K"));
      const raw = resolve(reference);
      const original =
        raw instanceof PDFArray ? raw.asArray() : reference ? [reference] : [];
      const children = node.kids.map((child) =>
        "kids" in child
          ? retain(child)
          : child.page === undefined || kept.has(child.page),
      );
      const values = original.filter((_, i) => children[i]);
      const keep =
        values.length > 0 ||
        (!original.length && (node.page === undefined || kept.has(node.page)));
      memo.set(node, keep);
      if (!keep) {
        removedTags.add(node.source);
        return false;
      }
      if (node.page !== undefined) {
        if (kept.has(node.page))
          node.source.set(k("Pg"), pages[node.page]!.ref);
        else node.source.delete(k("Pg"));
      }
      if (original.length)
        node.source.set(
          k("K"),
          node.array ? doc.context.obj(values) : values[0]!,
        );
      return true;
    }
    for (const n of tags.nodes.values()) retain(n);
    const rootReference = tags.root.get(k("K"));
    const rootRaw = resolve(rootReference);
    const roots =
      rootRaw instanceof PDFArray
        ? rootRaw.asArray()
        : rootReference
          ? [rootReference]
          : [];
    const remaining = roots.filter((_, i) => retain(tags.children[i]!));
    // Preserve an empty root and declarations when no tagged content survives.
    // Validation still rejects stranded marked content and parent entries.
    tags.root.set(k("K"), doc.context.obj(remaining));
    const used = new Set<number>();
    for (const [i, p] of pages.entries())
      if (kept.has(i)) {
        const index = resolve(p.node.get(k("StructParents")));
        if (index instanceof PDFNumber) used.add(index.asNumber());
        const annots = resolve(p.node.get(k("Annots")));
        if (annots instanceof PDFArray)
          for (const ref of annots.asArray()) {
            const a = resolve(ref);
            if (a instanceof PDFDict) {
              const v = resolve(a.get(k("StructParent")));
              if (v instanceof PDFNumber) used.add(v.asNumber());
            }
          }
      }
    const parents = entries(tags.root.get(k("ParentTree")), "Nums"),
      nums: PDFObject[] = [];
    for (let i = 0; i < parents.length; i += 2)
      if (used.has((resolve(parents[i]) as PDFNumber).asNumber()))
        nums.push(parents[i]!, parents[i + 1]!);
    tags.root.set(k("ParentTree"), doc.context.obj({ Nums: nums }));
    if (tags.root.has(k("IDTree"))) {
      const ids = entries(tags.root.get(k("IDTree")), "Names"),
        names: PDFObject[] = [];
      for (let i = 0; i < ids.length; i += 2)
        if (!removedTags.has(resolve(ids[i + 1]) as PDFDict))
          names.push(ids[i]!, ids[i + 1]!);
      tags.root.set(k("IDTree"), doc.context.obj({ Names: names }));
    }
  }
  function target(source: PDFDict, destination?: { page?: number }) {
    if (destination?.page !== undefined && !kept.has(destination.page)) {
      source.delete(k("Dest"));
      source.delete(k("A"));
    }
    if (removedTags.has(resolve(source.get(k("SE"))) as PDFDict))
      source.delete(k("SE"));
  }
  function bookmarks(list: typeof nav.bookmarks) {
    for (const b of list) {
      target(b.source, b.destination);
      bookmarks(b.children);
    }
  }
  bookmarks(nav.bookmarks);
  // Some exporters retain additional bookmark nodes through /Last or /Prev.
  // Preserve that graph, but apply the same explicit destination adjustment to
  // these nodes too; do not rebuild it from only the forward /First-/Next list.
  const outlineSeen = new Set<PDFDict>();
  function retainedOutline(raw: PDFObject | undefined) {
    const d = resolve(raw);
    if (!(d instanceof PDFDict) || outlineSeen.has(d)) return;
    outlineSeen.add(d);
    let destination = resolve(d.get(k("Dest")));
    const action = resolve(d.get(k("A")));
    if (
      !destination &&
      action instanceof PDFDict &&
      resolve(action.get(k("S"))) === k("GoTo")
    )
      destination = resolve(action.get(k("D")));
    if (destination instanceof PDFArray) {
      const page = pages.findIndex(
        (p) => p.node === resolve(destination.get(0)),
      );
      if (page >= 0) target(d, { page });
    }
    for (const name of ["First", "Last", "Next", "Prev"])
      retainedOutline(d.get(k(name)));
  }
  retainedOutline(doc.catalog.get(k("Outlines")));
  nav.links.forEach((links, i) => {
    if (kept.has(i))
      for (const link of links) target(link.source, link.target.destination);
  });
  if (nav.opening?.page !== undefined && !kept.has(nav.opening.page))
    doc.catalog.delete(k("OpenAction"));
  const deletedNames = new Set(
    nav.named
      .filter(([, d]) => d.page !== undefined && !kept.has(d.page))
      .map(([name]) => name),
  );
  const legacy = resolve(doc.catalog.get(k("Dests")));
  if (legacy instanceof PDFDict)
    for (const name of legacy.keys())
      if (deletedNames.has(`name:${name.decodeText()}`)) legacy.delete(name);
  const names = resolve(doc.catalog.get(k("Names")));
  if (names instanceof PDFDict && names.has(k("Dests"))) {
    const all = entries(names.get(k("Dests")), "Names"),
      retained: PDFObject[] = [];
    for (let i = 0; i < all.length; i += 2) {
      const name = resolve(all[i]) as PDFString | PDFHexString;
      if (!deletedNames.has(`string:${name.decodeText()}`))
        retained.push(all[i]!, all[i + 1]!);
    }
    names.set(k("Dests"), doc.context.obj({ Names: retained }));
  }
  // Supported forms are flat widgets; only remove the fields physically owned
  // by deleted pages. Shared/nested relationships still fail normal checks.
  const removedAnnotations = new Set<PDFObject>();
  pages.forEach((p, i) => {
    if (!kept.has(i)) {
      const a = resolve(p.node.get(k("Annots")));
      if (a instanceof PDFArray)
        for (const v of a.asArray()) {
          const d = resolve(v);
          if (d) removedAnnotations.add(d);
        }
    }
  });
  const form = resolve(doc.catalog.get(k("AcroForm")));
  if (form instanceof PDFDict) {
    const fields = resolve(form.get(k("Fields")));
    if (fields instanceof PDFArray)
      form.set(
        k("Fields"),
        doc.context.obj(
          fields.asArray().filter((v) => !removedAnnotations.has(resolve(v)!)),
        ),
      );
  }
}
