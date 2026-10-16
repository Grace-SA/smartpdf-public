import {
  PDFArray,
  PDFDict,
  PDFDocument,
  PDFHexString,
  PDFName,
  PDFNull,
  PDFNumber,
  PDFObject,
  PDFObjectCopier,
  PDFPage,
  PDFPageLeaf,
  PDFRef,
  PDFString,
} from "pdf-lib";
import { flatForm } from "../core/flat-form";
import { passiveAnnotations } from "../core/annotations";
import { passiveUriKind } from "../core/passive-uri";

type Destination =
  | { page: number; tail: PDFObject[] }
  | { unresolved: string; page?: never; tail?: never };
type Target = { destination?: Destination; action?: PDFDict };
type Bookmark = Target & {
  source: PDFDict;
  children: Bookmark[];
  open: boolean;
};
export type NavigationPlan = {
  links: { source: PDFDict; target: Target }[][];
  bookmarks: Bookmark[];
  labels: [number, PDFDict][];
  named: [string, Destination][];
  opening?: Destination;
  hasLabels: boolean;
};
export const navigationFailure =
  "This PDF has navigation that could not be preserved safely. Its links or bookmark targets may be incomplete or unsupported.";
const key = (s: string) => PDFName.of(s);
function fail(): never {
  throw new Error(navigationFailure);
}
const text = (object: PDFObject | undefined): string =>
  object instanceof PDFName
    ? object.decodeText()
    : object instanceof PDFString || object instanceof PDFHexString
      ? object.decodeText()
      : fail();

export function inspectNavigation(
  doc: PDFDocument,
  options: { preserveAnnotationExtensions?: boolean } = {},
): NavigationPlan {
  const pages = doc.getPages();
  const formPlan = flatForm(doc);
  const pageIndex = new Map(pages.map((p, i) => [p.node as PDFObject, i]));
  const resolve = (value: PDFObject | undefined): PDFObject | undefined => {
    if (!(value instanceof PDFRef)) return value;
    const result = doc.context.lookup(value);
    if (!result) fail();
    return result;
  };
  const dict = (value: PDFObject | undefined): PDFDict => {
    const object = resolve(value);
    return object instanceof PDFDict ? object : fail();
  };
  let nodes = 0;
  const guard = (depth: number) => {
    if (depth > 100 || ++nodes > 50000) fail();
  };
  const named = new Map<string, PDFObject>();
  const legacy = resolve(doc.catalog.get(key("Dests")));
  if (legacy)
    for (const [k, v] of dict(legacy).entries())
      named.set(`name:${k.decodeText()}`, v);
  const names = resolve(doc.catalog.get(key("Names")));
  // Other name trees are outside the supported navigation contract.
  if (names)
    for (const [k] of dict(names).entries())
      if (!["Dests", "EmbeddedFiles"].includes(k.decodeText())) fail();
  const treeSeen = new Set<PDFObject>();
  function tree(
    value: PDFObject,
    entryKey: "Names" | "Nums",
    callback: (k: PDFObject, v: PDFObject) => void,
    depth = 0,
  ) {
    guard(depth);
    const d = dict(value);
    if (treeSeen.has(d)) fail();
    treeSeen.add(d);
    const entries = resolve(d.get(key(entryKey))),
      kids = resolve(d.get(key("Kids")));
    if (entries && kids) fail();
    if (entries) {
      if (!(entries instanceof PDFArray) || entries.size() % 2) fail();
      for (let i = 0; i < entries.size(); i += 2) {
        guard(depth);
        callback(resolve(entries.get(i))!, entries.get(i + 1));
      }
    } else if (kids) {
      if (!(kids instanceof PDFArray)) fail();
      for (let i = 0; i < kids.size(); i++)
        tree(kids.get(i), entryKey, callback, depth + 1);
    } else fail();
  }
  const destTree = names && dict(names).get(key("Dests"));
  if (destTree)
    tree(destTree, "Names", (k, v) => {
      if (!(k instanceof PDFString || k instanceof PDFHexString)) fail();
      const name = `string:${text(k)}`;
      if (named.has(name)) fail();
      named.set(name, v);
    });
  function destination(
    value: PDFObject | undefined,
    seen = new Set<PDFObject>(),
    depth = 0,
  ): Destination {
    guard(depth);
    const d = resolve(value);
    if (!d || seen.has(d)) fail();
    seen.add(d);
    if (
      d instanceof PDFName ||
      d instanceof PDFString ||
      d instanceof PDFHexString
    ) {
      const prefix = d instanceof PDFName ? "name:" : "string:";
      const target = named.get(prefix + text(d));
      if (!target) return { unresolved: prefix + text(d) };
      return destination(target, seen, depth + 1);
    }
    if (d instanceof PDFDict)
      return destination(d.get(key("D")), seen, depth + 1);
    if (!(d instanceof PDFArray) || d.size() < 2) fail();
    const index = pageIndex.get(resolve(d.get(0))!);
    if (index === undefined) fail();
    const mode = resolve(d.get(1));
    if (!(mode instanceof PDFName)) fail();
    const sizes: Record<string, number> = {
      XYZ: 5,
      Fit: 2,
      FitH: 3,
      FitV: 3,
      FitR: 6,
      FitB: 2,
      FitBH: 3,
      FitBV: 3,
    };
    if (sizes[mode.decodeText()] !== d.size()) fail();
    const tail: PDFObject[] = [mode];
    for (let i = 2; i < d.size(); i++) {
      const n = resolve(d.get(i));
      if (n === PDFNull && mode.decodeText() !== "FitR") {
        tail.push(n);
        continue;
      }
      if (!(n instanceof PDFNumber) || !Number.isFinite(n.asNumber())) fail();
      tail.push(n);
    }
    return { page: index, tail };
  }
  function target(d: PDFDict): Target {
    const dest = d.get(key("Dest")),
      rawAction = d.get(key("A"));
    if (dest && rawAction) fail();
    if (dest) return { destination: destination(dest) };
    if (!rawAction) return {};
    const action = dict(rawAction),
      kind = text(resolve(action.get(key("S"))));
    if (action.has(key("Next"))) fail();
    if (kind === "GoTo")
      return { destination: destination(action.get(key("D"))), action };
    if (kind === "URI") {
      const uri = text(resolve(action.get(key("URI"))));
      const uriKind = passiveUriKind(uri);
      if (!uriKind || (uriKind === "relative" && doc.catalog.has(key("URI"))))
        fail();
      return { action };
    }
    return fail();
  }
  const links = pages.map((page) => {
    const raw = resolve(page.node.get(key("Annots")));
    if (!raw) return [];
    if (!(raw instanceof PDFArray)) fail();
    const result: { source: PDFDict; target: Target }[] = [];
    for (let i = 0; i < raw.size(); i++) {
      guard(0);
      const source = dict(raw.get(i));
      if (
        !passiveAnnotations.has(text(resolve(source.get(key("Subtype"))))) &&
        !formPlan?.widgets.has(source)
      )
        fail();
      const rect = resolve(source.get(key("Rect")));
      if (!(rect instanceof PDFArray) || rect.size() !== 4) fail();
      for (let j = 0; j < 4; j++) {
        const n = resolve(rect.get(j));
        if (!(n instanceof PDFNumber) || !Number.isFinite(n.asNumber())) fail();
      }
      const allowed = new Set([
        "Type",
        "Subtype",
        "Rect",
        "Contents",
        "NM",
        "M",
        "F",
        "AP",
        "AS",
        "Border",
        "C",
        "P",
        "A",
        "Dest",
        "H",
        "BS",
        "QuadPoints",
        "Lang",
        "OC",
        "StructParent",
        "T",
        "Subj",
        "CreationDate",
        "CA",
        "RC",
        "Popup",
        "IRT",
        "RT",
        "Open",
        "Name",
        "State",
        "StateModel",
        "Parent",
        "DA",
        "Q",
        "DS",
        "CL",
        "IT",
        "RD",
        "LE",
        "L",
        "IC",
        "LL",
        "LLE",
        "Cap",
        "LLO",
        "CP",
        "CO",
        "Vertices",
        "InkList",
        "Sy",
        "BE",
        "Rotate",
        "HighDpi",
        "AAPL:AKExtras",
        "AAPL:SFF",
      ]);
      if (formPlan?.widgets.has(source))
        for (const n of [
          "FT",
          "Ff",
          "V",
          "DV",
          "TU",
          "TM",
          "DA",
          "DR",
          "Q",
          "MaxLen",
          "MK",
        ])
          allowed.add(n);
      // Page-copy operations cannot remap unknown extension references safely.
      // Signing keeps every original page/object in the same document. Its
      // caller still runs probePdf over all extension values for active content,
      // missing references and resource limits before allowing preservation.
      if (!options.preserveAnnotationExtensions)
        for (const [k] of source.entries())
          if (!allowed.has(k.decodeText())) fail();
      result.push({ source, target: target(source) });
    }
    return result;
  });
  const owners = new Map<PDFDict, number>();
  links.forEach((list, page) =>
    list.forEach(({ source }) => {
      if (owners.has(source)) fail();
      owners.set(source, page);
    }),
  );
  for (const [annotation, page] of owners) {
    if (
      annotation.has(key("P")) &&
      resolve(annotation.get(key("P"))) !== pages[page]!.node
    )
      fail();
    for (const relation of ["Popup", "Parent", "IRT"]) {
      if (!annotation.has(key(relation))) continue;
      const other = dict(annotation.get(key(relation)));
      if (!owners.has(other)) fail();
      if (
        relation === "Popup" &&
        (text(resolve(other.get(key("Subtype")))) !== "Popup" ||
          resolve(other.get(key("Parent"))) !== annotation)
      )
        fail();
      if (
        relation === "Parent" &&
        (text(resolve(annotation.get(key("Subtype")))) !== "Popup" ||
          resolve(other.get(key("Popup"))) !== annotation)
      )
        fail();
    }
  }
  const outlineSeen = new Set<PDFObject>();
  function outlineList(raw: PDFObject | undefined, depth = 0): Bookmark[] {
    const result: Bookmark[] = [];
    while (raw) {
      guard(depth);
      const source = dict(raw);
      if (outlineSeen.has(source)) fail();
      outlineSeen.add(source);
      const title = resolve(source.get(key("Title")));
      if (!(title instanceof PDFString || title instanceof PDFHexString))
        fail();
      const allowed = new Set([
        "Title",
        "Parent",
        "Prev",
        "Next",
        "First",
        "Last",
        "Count",
        "SE",
        "Dest",
        "A",
        "C",
        "F",
      ]);
      for (const [k] of source.entries())
        if (!allowed.has(k.decodeText())) fail();
      const count = resolve(source.get(key("Count")));
      if (
        count &&
        (!(count instanceof PDFNumber) || !Number.isInteger(count.asNumber()))
      )
        fail();
      result.push({
        source,
        ...target(source),
        children: outlineList(source.get(key("First")), depth + 1),
        open: !count || (count as PDFNumber).asNumber() >= 0,
      });
      raw = source.get(key("Next"));
    }
    return result;
  }
  const outlines = resolve(doc.catalog.get(key("Outlines")));
  const bookmarks = outlines
    ? outlineList(dict(outlines).get(key("First")))
    : [];
  const labels: [number, PDFDict][] = [];
  const rawLabels = doc.catalog.get(key("PageLabels"));
  if (rawLabels)
    tree(rawLabels, "Nums", (k, v) => {
      if (
        !(k instanceof PDFNumber) ||
        !Number.isInteger(k.asNumber()) ||
        k.asNumber() < 0 ||
        k.asNumber() >= pages.length
      )
        fail();
      if (labels.some(([i]) => i === k.asNumber())) fail();
      const value = dict(v);
      for (const [name] of value.entries())
        if (!["S", "P", "St"].includes(name.decodeText())) fail();
      const style = resolve(value.get(key("S"))),
        prefix = resolve(value.get(key("P"))),
        start = resolve(value.get(key("St")));
      if (
        style &&
        (!(style instanceof PDFName) ||
          !["D", "R", "r", "A", "a"].includes(style.decodeText()))
      )
        fail();
      if (
        prefix &&
        !(prefix instanceof PDFString || prefix instanceof PDFHexString)
      )
        fail();
      if (
        start &&
        (!(start instanceof PDFNumber) ||
          !Number.isInteger(start.asNumber()) ||
          start.asNumber() < 1)
      )
        fail();
      labels.push([k.asNumber(), value]);
    });
  labels.sort((a, b) => a[0] - b[0]);
  if (!labels.length || labels[0]![0] !== 0)
    labels.unshift([0, doc.context.obj({ S: "D", St: 1 })]);
  const opening = doc.catalog.get(key("OpenAction"));
  return {
    links,
    bookmarks,
    labels,
    hasLabels: !!rawLabels,
    named: [...named].map(([name, value]) => {
      const d = destination(value);
      if ("unresolved" in d) fail();
      return [name, d];
    }),
    ...(opening ? { opening: destination(opening) } : {}),
  };
}

export async function copyWithNavigation(
  output: PDFDocument,
  source: PDFDocument,
  plan: NavigationPlan,
  inputIndex: number,
) {
  // Remove annotation back-references before page copying so the library cannot
  // create duplicate, detached pages through a link's /P or destination.
  const sourcePages = source.getPages(),
    saved = sourcePages.map((p) => p.node.get(key("Annots")));
  sourcePages.forEach((p) => p.node.delete(key("Annots")));
  let pages;
  const copier = PDFObjectCopier.for(source.context, output.context);
  try {
    pages = sourcePages.map((page) => {
      const ref = copier.copy(page.ref);
      return PDFPage.of(
        output.context.lookup(ref, PDFDict) as PDFPageLeaf,
        ref,
        output,
      );
    });
  } finally {
    sourcePages.forEach((p, i) => {
      if (saved[i]) p.node.set(key("Annots"), saved[i]!);
    });
  }
  const offset = output.getPageCount();
  for (const p of pages) output.addPage(p);
  const destination = (d: Destination) =>
    "unresolved" in d
      ? PDFHexString.fromText(
          `unresolved-document-${inputIndex + 1}:${d.unresolved}`,
        )
      : output.context.obj([
          pages[d.page]!.ref,
          ...d.tail.map((v) => copier.copy(v)),
        ]);
  const writeTarget = (out: PDFDict, t: Target) => {
    if (t.action) {
      const action = PDFDict.withContext(output.context);
      for (const [k, v] of t.action.entries())
        if (k.decodeText() !== "D") action.set(k, copier.copy(v));
      if (t.destination) action.set(key("D"), destination(t.destination));
      out.set(key("A"), action);
    } else if (t.destination) out.set(key("Dest"), destination(t.destination));
  };
  const annotations = new Map<PDFDict, PDFRef>();
  for (const list of plan.links)
    for (const { source } of list)
      annotations.set(
        source,
        output.context.register(PDFDict.withContext(output.context)),
      );
  plan.links.forEach((links, index) => {
    if (!links.length) return;
    const refs = links.map((link) => {
      const ref = annotations.get(link.source)!;
      const d = output.context.lookup(ref, PDFDict);
      for (const [k, v] of link.source.entries())
        if (["Popup", "Parent", "IRT"].includes(k.decodeText()))
          d.set(k, annotations.get(source.context.lookup(v, PDFDict))!);
        else if (!["P", "Dest", "A", "StructParent"].includes(k.decodeText()))
          d.set(k, copier.copy(v));
      d.set(key("P"), pages[index]!.ref);
      writeTarget(d, link.target);
      return ref;
    });
    pages[index]!.node.set(key("Annots"), output.context.obj(refs));
  });
  type Node = { dict: PDFDict; ref: PDFRef; children: Node[]; open: boolean };
  const structureLinks: { output: PDFDict; source: PDFDict }[] = [];
  function build(items: Bookmark[]): Node[] {
    return items.map((item) => {
      const d = PDFDict.withContext(output.context);
      for (const name of ["Title", "C", "F"]) {
        const value = item.source.get(key(name));
        if (value) d.set(key(name), copier.copy(value));
      }
      writeTarget(d, item);
      if (item.source.has(key("SE")))
        structureLinks.push({
          output: d,
          source: source.context.lookup(item.source.get(key("SE")), PDFDict),
        });
      return {
        dict: d,
        ref: output.context.register(d),
        children: build(item.children),
        open: item.open,
      };
    });
  }
  // Each returned node belongs to the output context; source documents can be released.
  const bookmarks = build(plan.bookmarks);
  const labels = plan.labels.map(
    ([i, d]) => [offset + i, copier.copy(d)] as const,
  );
  const named = plan.named.map(
    ([name, d]) =>
      [
        PDFHexString.fromText(`document-${inputIndex + 1}:${name}`),
        destination(d),
      ] as const,
  );
  if (inputIndex === 0 && plan.opening)
    output.catalog.set(key("OpenAction"), destination(plan.opening));
  return {
    bookmarks,
    structureLinks,
    labels,
    named,
    hasLabels: plan.hasLabels,
    copier,
    annotations,
    pages,
    offset,
  };
}

export function finishNavigation(
  output: PDFDocument,
  parts: Awaited<ReturnType<typeof copyWithNavigation>>[],
) {
  type Node = Awaited<
    ReturnType<typeof copyWithNavigation>
  >["bookmarks"][number];
  const root = output.context.obj({ Type: "Outlines" }),
    rootRef = output.context.register(root);
  const visible = (nodes: Node[]): number =>
    nodes.reduce(
      (n, node) => n + 1 + (node.open ? visible(node.children) : 0),
      0,
    );
  function link(nodes: Node[], parent: PDFRef) {
    nodes.forEach((node, i) => {
      node.dict.set(key("Parent"), parent);
      if (i) node.dict.set(key("Prev"), nodes[i - 1]!.ref);
      if (i + 1 < nodes.length) node.dict.set(key("Next"), nodes[i + 1]!.ref);
      if (node.children.length) {
        node.dict.set(key("First"), node.children[0]!.ref);
        node.dict.set(key("Last"), node.children.at(-1)!.ref);
        node.dict.set(
          key("Count"),
          PDFNumber.of((node.open ? 1 : -1) * visible(node.children)),
        );
        link(node.children, node.ref);
      }
    });
  }
  const nodes = parts.flatMap((p) => p.bookmarks);
  if (nodes.length) {
    link(nodes, rootRef);
    root.set(key("First"), nodes[0]!.ref);
    root.set(key("Last"), nodes.at(-1)!.ref);
    root.set(key("Count"), PDFNumber.of(visible(nodes)));
    output.catalog.set(key("Outlines"), rootRef);
  }
  if (parts.some((p) => p.hasLabels))
    output.catalog.set(
      key("PageLabels"),
      output.context.obj({
        Nums: parts.flatMap((p) =>
          p.labels.flatMap(([i, d]) => [PDFNumber.of(i), d]),
        ),
      }),
    );
  const names = parts
    .flatMap((p) => p.named)
    .sort((a, b) =>
      a[0].decodeText() < b[0].decodeText()
        ? -1
        : a[0].decodeText() > b[0].decodeText()
          ? 1
          : 0,
    );
  if (names.length)
    output.catalog.set(
      key("Names"),
      output.context.obj({
        Dests: { Names: names.flatMap(([k, v]) => [k, v]) },
      }),
    );
}
