import {
  PDFDocument,
  PDFDict,
  PDFArray,
  PDFName,
  PDFNumber,
  PDFNull,
  PDFObject,
  PDFBool,
  PDFPage,
  PDFObjectCopier,
  PDFRef,
  PDFString,
  PDFHexString,
} from "pdf-lib";
import { key, reader } from "./structure";
import { normalizeOptionalTagIndexes } from "../core/optional-tag-indexes";
import { hasPageMcids } from "./inert-tag-index";
type Content = { mcid: number; page?: number; source?: PDFDict };
type ObjectContent = { object: PDFDict; page: number; source: PDFDict };
type Node = {
  source: PDFDict;
  page?: number;
  kids: (Node | Content | ObjectContent)[];
  array: boolean;
};
const standardRoles = new Set(
  "Document Part Art Sect Div BlockQuote Caption TOC TOCI Index NonStruct Private P H H1 H2 H3 H4 H5 H6 L LI Lbl LBody Table TR TH TD THead TBody TFoot Span Quote Note Reference BibEntry Code Link Annot Ruby RB RT RP Warichu WT WP Figure Formula Form".split(
    " ",
  ),
);
export function inspectTags(doc: PDFDocument) {
  normalizeOptionalTagIndexes(doc);
  const r = reader(doc, "tagged"),
    pages = doc.getPages();
  const rootValue = doc.catalog.get(key("StructTreeRoot"));
  const annotationPages = new Map<PDFDict, number>();
  pages.forEach((p, i) => {
    if (p.node.has(key("Annots")))
      for (const v of r.array(p.node.get(key("Annots"))))
        annotationPages.set(r.dict(v), i);
  });
  if (!rootValue) {
    const rawMark = doc.catalog.get(key("MarkInfo"));
    const mark = rawMark ? r.dict(rawMark) : undefined;
    const untagged =
      mark &&
      r.resolve(mark.get(key("Marked"))) === PDFBool.False &&
      mark.keys().every((k) => ["Type", "Marked"].includes(k.decodeText()));
    if (
      (rawMark && !untagged) ||
      [...annotationPages.keys()].some((a) => a.has(key("StructParent"))) ||
      pages.some((p) => {
        if (!p.node.has(key("StructParents"))) return false;
        const index = r.resolve(p.node.get(key("StructParents")));
        return (
          !(index instanceof PDFNumber) ||
          !Number.isSafeInteger(index.asNumber()) ||
          index.asNumber() < 0 ||
          hasPageMcids(doc, p)
        );
      })
    )
      r.fail("This PDF declares tags but its structure tree is missing.");
    return undefined;
  }
  const root = r.dict(rootValue);
  r.keys(root, [
    "Type",
    "K",
    "ParentTree",
    "ParentTreeNextKey",
    "RoleMap",
    "ClassMap",
    "IDTree",
    "Namespaces",
  ]);
  const namespaces = root.has(key("Namespaces"))
    ? r.array(root.get(key("Namespaces")))
    : [];
  const namespaceDicts = new Set<PDFDict>();
  for (const value of namespaces) {
    if (!(value instanceof PDFRef))
      r.fail("A tag namespace must be an indirect dictionary.");
    const ns = r.dict(value);
    r.keys(ns, ["Type", "NS"]);
    const uri = r.resolve(ns.get(key("NS")));
    if (
      !(uri instanceof PDFString || uri instanceof PDFHexString) ||
      !["http://iso.org/pdf/ssn", "http://iso.org/pdf2/ssn"].includes(
        uri.decodeText(),
      )
    )
      r.fail("This tag namespace cannot be preserved yet.");
    if (ns.has(key("Type")) && r.name(ns.get(key("Type"))) !== "Namespace")
      r.fail("Invalid namespace type.");
    namespaceDicts.add(ns);
  }
  const rawMark = doc.catalog.get(key("MarkInfo"));
  const mark = rawMark
    ? r.dict(rawMark)
    : doc.context.obj({ Marked: true, Suspects: true });
  r.keys(mark, ["Type", "Marked", "Suspects", "UserProperties"]);
  if (r.resolve(mark.get(key("Marked"))) !== PDFBool.True)
    r.fail("This PDF has inconsistent tagged-document markers.");
  for (const n of ["Suspects", "UserProperties"])
    if (mark.has(key(n)) && !(r.resolve(mark.get(key(n))) instanceof PDFBool))
      r.fail("This PDF has invalid tagged-document flags.");
  const pageMap = new Map(pages.map((p, i) => [p.node, i]));
  const page = (v: PDFObject) => {
    const i = pageMap.get(r.dict(v) as (typeof pages)[number]["node"]);
    return i === undefined
      ? r.fail("A tag points to a page outside this document.")
      : i;
  };
  const roles = root.has(key("RoleMap"))
    ? r.dict(root.get(key("RoleMap")))
    : undefined;
  const classes = root.has(key("ClassMap"))
    ? r.dict(root.get(key("ClassMap")))
    : undefined;
  const unmappedRoles = new Set<string>();
  function role(n: string, seen = new Set<string>()) {
    if (!n) r.fail("This PDF has a missing or invalid tag role.");
    if (seen.has(n)) r.fail("This PDF has a cyclic tag role mapping.");
    seen.add(n);
    if (roles?.has(key(n))) return role(r.name(roles.get(key(n))), seen);
    // Preserve an unknown terminal role as supplied, without inventing a
    // standard semantic mapping. Structural consistency is still required.
    if (!standardRoles.has(n)) unmappedRoles.add(n);
  }
  if (roles) for (const [n] of roles.entries()) role(n.decodeText());
  const seen = new Map<PDFDict, Node>();
  const activeKids = new Set<PDFDict>();
  let incompleteIndex = false;
  let count = 0;
  const uses = new Map<string, Set<PDFDict>>();
  const sourceParents = new Map<PDFDict, PDFDict | undefined>();
  let nonTreeParent = false;
  const objectUses = new Map<
    PDFDict,
    { owner: PDFDict; page: number; indexed?: boolean }
  >();
  const ids = new Map<string, PDFDict>();
  const stringKey = (v: PDFObject | undefined): string => {
    const s = r.resolve(v);
    if (!(s instanceof PDFString || s instanceof PDFHexString))
      return r.fail("Invalid structure identifier.");
    return Array.from(s.asBytes(), (n) => n.toString(16).padStart(2, "0")).join(
      "",
    );
  };
  function content(
    mcid: PDFObject | undefined,
    p: number | undefined,
    owner: PDFDict,
    source?: PDFDict,
  ): Content {
    const n = r.resolve(mcid);
    if (
      !(n instanceof PDFNumber) ||
      !Number.isInteger(n.asNumber()) ||
      n.asNumber() < 0
    )
      r.fail("This PDF has a content tag without a valid page and MCID.");
    if (p === undefined) {
      incompleteIndex = true;
      return { mcid: (n as PDFNumber).asNumber(), source };
    }
    const number = (n as PDFNumber).asNumber(),
      id = `${p}:${number}`;
    const owners = uses.get(id) ?? new Set<PDFDict>();
    owners.add(owner);
    uses.set(id, owners);
    return { mcid: number, page: p!, source };
  }
  function child(
    value: PDFObject,
    parent: PDFDict,
    inherited: number | undefined,
    depth: number,
  ): Node | Content | ObjectContent {
    if (++count > 50000 || depth > 100)
      r.fail("This PDF's tag tree is too complex.");
    const v = r.resolve(value);
    if (v instanceof PDFNumber) return content(v, inherited, parent);
    const d = r.dict(v),
      p = d.has(key("Pg")) ? page(d.get(key("Pg"))!) : inherited;
    if (r.name(d.get(key("Type"))) === "OBJR") {
      r.keys(d, ["Type", "Pg", "Obj"]);
      const object = r.dict(d.get(key("Obj")));
      const objectPage = annotationPages.get(object);
      if (
        objectPage === undefined ||
        (p !== undefined && p !== objectPage) ||
        objectUses.has(object)
      )
        r.fail("Invalid or repeated annotation tag reference.");
      objectUses.set(object, { owner: parent, page: objectPage! });
      return { object, page: objectPage!, source: d };
    }
    if (r.name(d.get(key("Type"))) === "MCR") {
      r.keys(d, ["Type", "Pg", "MCID"]);
      return content(d.get(key("MCID")), p, parent, d);
    }
    if (activeKids.has(d)) r.fail("This PDF has cyclic tag children.");
    if (seen.has(d)) {
      const prior = seen.get(d)!;
      if (prior.page !== p) r.fail("A shared tag inherits conflicting pages.");
      return prior;
    }
    r.keys(d, [
      "Type",
      "S",
      "P",
      "K",
      "Pg",
      "A",
      "C",
      "R",
      "T",
      "Lang",
      "Alt",
      "ActualText",
      "E",
      "ID",
      "NS",
    ]);
    const t = r.name(d.get(key("Type")));
    if (t && t !== "StructElem")
      r.fail("This PDF uses unsupported object-reference or extended tags.");
    const rawParent = r.resolve(d.get(key("P")));
    const sourceParent =
      !rawParent || rawParent === PDFNull ? undefined : r.dict(rawParent);
    sourceParents.set(d, sourceParent);
    if (sourceParent !== parent) nonTreeParent = true;
    if (d.has(key("NS"))) {
      if (!namespaceDicts.has(r.dict(d.get(key("NS")))))
        r.fail("Missing declared tag namespace.");
      if (!r.name(d.get(key("S")))) r.fail("Missing namespaced tag role.");
    } else role(r.name(d.get(key("S"))));
    const c = d.get(key("C"));
    if (c) {
      const a = r.resolve(c) instanceof PDFArray ? r.array(c) : [c];
      for (const x of a) {
        const v = r.resolve(x);
        if (v instanceof PDFNumber) continue;
        if (!(v instanceof PDFName) || !classes?.has(v))
          r.fail("This PDF references a missing tag attribute class.");
      }
    }
    const raw = d.get(key("K"));
    const node: Node = {
      source: d,
      page: p,
      kids: [],
      array: r.resolve(raw) instanceof PDFArray,
    };
    seen.set(d, node);
    activeKids.add(d);
    if (d.has(key("ID"))) {
      const id = stringKey(d.get(key("ID")));
      if (ids.has(id)) r.fail("Duplicate structure identifier.");
      ids.set(id, d);
    }
    if (raw && r.resolve(raw) !== PDFNull)
      node.kids = (node.array ? r.array(raw) : [raw]).map((v) =>
        child(v, d, p, depth + 1),
      );
    activeKids.delete(d);
    return node;
  }
  const rawKids = root.get(key("K"));
  if (!rawKids) r.fail("This PDF's tag tree has no structure children.");
  const children = (
    r.resolve(rawKids) instanceof PDFArray ? r.array(rawKids) : [rawKids!]
  ).map((v) => child(v, root, undefined, 0));
  if (children.some((v) => !("kids" in v)))
    r.fail("This PDF has invalid top-level tags.");
  // A split can retain only pages without tagged content. Keep the empty root
  // and its declarations, but never accept stranded marked content as empty.
  if (!children.length && pages.some((p) => hasPageMcids(doc, p)))
    r.fail("Marked page content has no structure children.");
  const parentValues = new Map<number, PDFObject>(),
    treeSeen = new Set<PDFDict>();
  function tree(value: PDFObject | undefined, depth = 0) {
    if (depth > 100) r.fail("This PDF's tag parent tree is too complex.");
    const d = r.dict(value);
    if (treeSeen.has(d)) r.fail("This PDF has a cyclic tag parent tree.");
    treeSeen.add(d);
    r.keys(d, ["Type", "Nums", "Kids", "Limits"]);
    if (d.has(key("Type")) && r.name(d.get(key("Type"))) !== "ParentTree")
      r.fail("Invalid tag parent tree type.");
    if (d.has(key("Nums")) && d.has(key("Kids")))
      r.fail("This PDF has an ambiguous tag parent tree.");
    if (d.has(key("Nums"))) {
      const a = r.array(d.get(key("Nums")));
      if (a.length % 2) r.fail("Invalid tag parent entries.");
      for (let i = 0; i < a.length; i += 2) {
        const n = r.resolve(a[i]);
        if (
          !(n instanceof PDFNumber) ||
          !Number.isInteger(n.asNumber()) ||
          n.asNumber() < 0 ||
          parentValues.has(n.asNumber())
        )
          r.fail("Invalid or repeated tag parent index.");
        parentValues.set((n as PDFNumber).asNumber(), a[i + 1]!);
      }
    } else if (d.has(key("Kids")))
      r.array(d.get(key("Kids"))).forEach((v) => tree(v, depth + 1));
    else r.fail("Missing tag parent entries.");
  }
  const parentIndex = r.resolve(root.get(key("ParentTree")));
  if (parentIndex && parentIndex !== PDFNull) tree(parentIndex);
  else if (objectUses.size) r.fail("Content tags require a parent index.");
  const parents: { page: number; entries: (PDFDict | undefined)[] }[] = [];
  // Preserve content-indexed leaf tags outside /K without inventing reading order.
  const detached: { node: Node; parent?: PDFDict }[] = [];
  const usedKeys = new Set<number>(),
    verified = new Set<string>();
  pages.forEach((p, i) => {
    const raw = p.node.get(key("StructParents"));
    if (!raw) return;
    const n = r.resolve(raw);
    if (
      !(n instanceof PDFNumber) ||
      !Number.isInteger(n.asNumber()) ||
      n.asNumber() < 0 ||
      usedKeys.has(n.asNumber())
    )
      r.fail("A page has an invalid or shared tag parent index.");
    const index = (n as PDFNumber).asNumber();
    if (!parentValues.has(index)) {
      if (hasPageMcids(doc, p))
        r.fail("Marked page content has no parent index.");
      incompleteIndex = true;
      return;
    }
    usedKeys.add(index);
    const entries = r.array(parentValues.get(index)).map((v, mcid) => {
      if (r.resolve(v) === PDFNull) return undefined;
      const d = r.dict(v),
        id = `${i}:${mcid}`;
      if (!seen.has(d)) {
        const parent = r.resolve(d.get(key("P")));
        if (parent && parent !== PDFNull && !(parent instanceof PDFDict))
          r.fail("A detached tag parent is outside the preserved graph.");
        const candidate = child(
          d,
          parent instanceof PDFDict ? parent : root,
          undefined,
          0,
        );
        if (!("kids" in candidate))
          r.fail("An indexed tag must be a structure element.");
        detached.push({
          node: candidate as Node,
          parent: parent instanceof PDFDict ? parent : undefined,
        });
      }
      if (!uses.get(id)?.has(d)) incompleteIndex = true;
      verified.add(id);
      return d;
    });
    parents.push({ page: i, entries });
  });
  for (const [annotation] of annotationPages) {
    const raw = annotation.get(key("StructParent"));
    const use = objectUses.get(annotation);
    if (!raw && !use) continue;
    if (!raw && use) {
      incompleteIndex = true;
      continue;
    }
    const n = r.resolve(raw);
    if (
      !use ||
      !(n instanceof PDFNumber) ||
      !Number.isInteger(n.asNumber()) ||
      n.asNumber() < 0 ||
      usedKeys.has(n.asNumber()) ||
      r.resolve(parentValues.get(n.asNumber())) !== use.owner
    )
      r.fail("The annotation tag and parent tree disagree.");
    usedKeys.add((n as PDFNumber).asNumber());
    use!.indexed = true;
  }
  const unindexed = [...uses.keys()].filter((id) => !verified.has(id));
  if (unindexed.length) incompleteIndex = true;
  if (usedKeys.size !== parentValues.size)
    r.fail("This PDF has orphaned or unsupported tag parent entries.");
  // Preserve ancestors reachable only through P, without inserting them into
  // the document's K reading order. All their references undergo normal checks.
  for (const node of seen.keys()) {
    const parent = sourceParents.get(node);
    if (parent && parent !== root && !seen.has(parent))
      child(parent, root, undefined, 0);
  }
  for (const node of seen.keys()) {
    const chain = new Set<PDFDict>();
    let current: PDFDict | undefined = node;
    while (current && current !== root) {
      if (!seen.has(current) || chain.has(current) || chain.size > 100)
        r.fail("A tag parent is outside the preserved structure or cyclic.");
      chain.add(current);
      current = sourceParents.get(current);
    }
  }
  const idSeen = new Set<string>(),
    idTrees = new Set<PDFDict>();
  function idTree(value: PDFObject, depth = 0) {
    if (depth > 100) r.fail("Structure identifier tree is too deep.");
    const d = r.dict(value);
    if (idTrees.has(d)) r.fail("Cyclic structure identifier tree.");
    idTrees.add(d);
    r.keys(d, ["Names", "Kids", "Limits"]);
    if (d.has(key("Names")) === d.has(key("Kids")))
      r.fail("Invalid structure identifier tree.");
    if (d.has(key("Kids")))
      for (const v of r.array(d.get(key("Kids")))) idTree(v, depth + 1);
    else {
      const a = r.array(d.get(key("Names")));
      if (a.length % 2) r.fail("Invalid structure identifiers.");
      for (let i = 0; i < a.length; i += 2) {
        const id = stringKey(a[i]);
        if (
          idSeen.has(id) ||
          !ids.has(id) ||
          r.resolve(a[i + 1]) !== ids.get(id)
        )
          r.fail("Structure identifier mapping disagrees.");
        idSeen.add(id);
      }
    }
  }
  const identifierIndex = r.resolve(root.get(key("IDTree")));
  if (identifierIndex && identifierIndex !== PDFNull) idTree(identifierIndex);
  if (idSeen.size !== ids.size)
    r.fail("Structure identifiers are missing from the identifier tree.");
  return {
    children: children as Node[],
    nodes: seen,
    parents,
    detached,
    roles,
    classes,
    mark,
    objectUses,
    ids,
    unmappedRoles,
    root,
    sourceParents,
    namespaces,
    incomplete:
      incompleteIndex ||
      nonTreeParent ||
      unindexed.length > 0 ||
      [...uses.values()].some((owners) => owners.size > 1),
    language: doc.catalog.get(key("Lang")),
  };
}
export function copyTags(
  output: PDFDocument,
  plan: ReturnType<typeof inspectTags>,
  copier: PDFObjectCopier,
  pages: PDFPage[],
  inputIndex: number,
  nextKey: number,
  annotations: Map<PDFDict, PDFRef> = new Map(),
) {
  if (!plan) return undefined;
  const sourceParents = plan.sourceParents,
    sourceRoot = plan.root;
  const roleMap = plan.roles;
  const renamed = (n: PDFName) =>
    key(`document-${inputIndex + 1}:${n.decodeText()}`);
  const refs = new Map<PDFDict, PDFRef>(),
    dicts = new Map<PDFDict, PDFDict>();
  for (const [source] of plan.nodes) {
    const d = PDFDict.withContext(output.context);
    dicts.set(source, d);
    refs.set(source, output.context.register(d));
  }
  const wrapper = output.context.obj({ Type: "StructElem", S: "Document" }),
    wrapperRef = output.context.register(wrapper);
  if (plan.language) wrapper.set(key("Lang"), copier.copy(plan.language));
  const written = new Set<PDFDict>();
  function write(node: Node) {
    if (written.has(node.source)) return;
    written.add(node.source);
    const d = dicts.get(node.source)!;
    for (const [k, v] of node.source.entries())
      if (!["P", "K", "Pg", "S", "C", "ID"].includes(k.decodeText()))
        d.set(k, copier.copy(v));
    d.set(key("Type"), key("StructElem"));
    const originalParent = sourceParents.get(node.source);
    if (originalParent)
      d.set(
        key("P"),
        originalParent === sourceRoot ? wrapperRef : refs.get(originalParent)!,
      );
    else if (node.source.get(key("P"), true) === PDFNull)
      d.set(key("P"), PDFNull);
    const role = node.source.lookup(key("S"), PDFName);
    d.set(
      key("S"),
      !node.source.has(key("NS")) && roleMap?.has(role) ? renamed(role) : role,
    );
    const classes = node.source.get(key("C"));
    if (classes) {
      const value = node.source.context.lookup(classes);
      const renameClass = (v: PDFObject) => {
        const n = node.source.context.lookup(v);
        return n instanceof PDFName ? renamed(n) : copier.copy(v);
      };
      d.set(
        key("C"),
        value instanceof PDFArray
          ? output.context.obj(value.asArray().map(renameClass))
          : renameClass(classes),
      );
    }
    if (node.source.has(key("Pg")) && node.page !== undefined)
      d.set(key("Pg"), pages[node.page]!.ref);
    const kids = node.kids.map((child) => {
      if ("kids" in child) {
        write(child);
        return refs.get(child.source)!;
      }
      if ("object" in child) {
        const ref = annotations.get(child.object);
        if (!ref) throw new Error("Missing copied annotation for tag.");
        return output.context.obj({
          Type: "OBJR",
          ...(child.source.has(key("Pg"))
            ? { Pg: pages[child.page]!.ref }
            : {}),
          Obj: ref,
        });
      }
      if (!child.source) return PDFNumber.of(child.mcid);
      return output.context.obj({
        Type: "MCR",
        ...(child.source.has(key("Pg")) && child.page !== undefined
          ? { Pg: pages[child.page]!.ref }
          : {}),
        MCID: child.mcid,
      });
    });
    if (node.source.get(key("K"), true) !== undefined)
      d.set(
        key("K"),
        node.array ? output.context.obj(kids) : (kids[0] ?? PDFNull),
      );
  }
  for (const node of plan.nodes.values()) write(node);
  wrapper.set(
    key("K"),
    output.context.obj(plan.children.map((n) => refs.get(n.source)!)),
  );
  const nums: PDFObject[] = [];
  const identifiers: [string, PDFRef][] = [];
  for (const [id, source] of plan.ids) {
    const renamedId = `document-${inputIndex + 1}:${id}`;
    dicts.get(source)!.set(key("ID"), PDFHexString.fromText(renamedId));
    identifiers.push([renamedId, refs.get(source)!]);
  }
  for (const p of plan.parents) {
    const n = nextKey++;
    pages[p.page]!.node.set(key("StructParents"), PDFNumber.of(n));
    nums.push(
      PDFNumber.of(n),
      output.context.obj(p.entries.map((d) => (d ? refs.get(d)! : PDFNull))),
    );
  }
  for (const [annotation, use] of plan.objectUses) {
    if (!use.indexed) continue;
    const ref = annotations.get(annotation);
    if (!ref) throw new Error("Missing copied annotation.");
    const n = nextKey++;
    output.context
      .lookup(ref, PDFDict)
      .set(key("StructParent"), PDFNumber.of(n));
    nums.push(PDFNumber.of(n), refs.get(use.owner)!);
  }
  const roles = PDFDict.withContext(output.context),
    classes = PDFDict.withContext(output.context);
  if (plan.roles)
    for (const [k, v] of plan.roles.entries()) {
      const name = plan.roles.context.lookup(v, PDFName);
      roles.set(renamed(k), plan.roles.has(name) ? renamed(name) : name);
    }
  if (plan.classes)
    for (const [k, v] of plan.classes.entries())
      classes.set(renamed(k), copier.copy(v));
  return {
    wrapper,
    refs,
    wrapperRef,
    nums,
    identifiers,
    namespaces: plan.namespaces.map((v) => copier.copy(v)),
    roles,
    classes,
    nextKey,
    unmappedRoles: plan.unmappedRoles,
    suspects:
      plan.incomplete ||
      plan.detached.length > 0 ||
      plan.unmappedRoles.size > 0 ||
      plan.mark.context.lookup(plan.mark.get(key("Suspects"))) === PDFBool.True,
    userProperties:
      plan.mark.context.lookup(plan.mark.get(key("UserProperties"))) ===
      PDFBool.True,
  };
}
export function finishTags(
  output: PDFDocument,
  parts: ReturnType<typeof copyTags>[],
) {
  const tags = parts.filter((p) => !!p);
  if (!tags.length) return;
  const root = output.context.obj({
    Type: "StructTreeRoot",
    K: tags.map((p) => p.wrapperRef),
    ParentTree: { Nums: tags.flatMap((p) => p.nums) },
    ParentTreeNextKey: tags.at(-1)!.nextKey,
  });
  const rootRef = output.context.register(root);
  const namespaces = tags.flatMap((t) => t.namespaces);
  if (namespaces.length) {
    root.set(key("Namespaces"), output.context.obj(namespaces));
    output.catalog.set(key("Version"), key("2.0"));
  }
  const identifiers = tags
    .flatMap((p) => p.identifiers)
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  if (identifiers.length)
    root.set(
      key("IDTree"),
      output.context.obj({
        Names: identifiers.flatMap(([id, ref]) => [
          PDFHexString.fromText(id),
          ref,
        ]),
      }),
    );
  for (const p of tags) p.wrapper.set(key("P"), rootRef);
  for (const [name, field] of [
    ["RoleMap", "roles"],
    ["ClassMap", "classes"],
  ] as const) {
    const d = PDFDict.withContext(output.context);
    for (const p of tags) for (const [k, v] of p[field].entries()) d.set(k, v);
    if (
      field === "roles" &&
      tags.some((p) => [...p.unmappedRoles].some((n) => d.has(key(n))))
    )
      throw new Error("Custom tag names conflict with the combined role map.");
    if (d.keys().length) root.set(key(name), d);
  }
  output.catalog.set(key("StructTreeRoot"), rootRef);
  output.catalog.set(
    key("MarkInfo"),
    output.context.obj({
      Marked: true,
      Suspects: tags.length !== parts.length || tags.some((t) => t.suspects),
      UserProperties: tags.some((t) => t.userProperties),
    }),
  );
}
