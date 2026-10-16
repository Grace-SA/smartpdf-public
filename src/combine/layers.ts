import {
  PDFDocument,
  PDFDict,
  PDFArray,
  PDFString,
  PDFHexString,
  PDFObject,
  PDFObjectCopier,
  PDFStream,
} from "pdf-lib";
import { key, reader } from "./structure";
export function inspectLayers(doc: PDFDocument) {
  const r = reader(doc, "layers");
  const raw = doc.catalog.get(key("OCProperties"));
  const groups: PDFObject[] = [];
  let config: PDFDict | undefined;
  if (raw) {
    const oc = r.dict(raw);
    r.keys(oc, ["OCGs", "D"]);
    groups.push(...r.array(oc.get(key("OCGs"))));
    // Empty, complete configurations occur in ordinary office exports. All
    // references below must still resolve to registered groups, even when zero.
    config = r.dict(oc.get(key("D")));
    r.keys(config, [
      "Name",
      "Creator",
      "BaseState",
      "ON",
      "OFF",
      "Intent",
      "AS",
      "Order",
      "ListMode",
      "RBGroups",
      "Locked",
    ]);
    const base = r.name(config.get(key("BaseState")));
    if (base && !["ON", "OFF"].includes(base))
      r.fail(
        "Layers with an inherited previous state cannot be preserved yet.",
      );
    const intent = config.get(key("Intent"));
    if (
      intent &&
      r.name(intent) !== "View" &&
      !(
        r.resolve(intent) instanceof PDFArray &&
        r.array(intent).every((v) => r.name(v) === "View")
      )
    )
      r.fail(
        "This PDF uses a non-default layer intent that cannot be combined yet.",
      );
    const list = r.name(config.get(key("ListMode")));
    if (list && list !== "AllPages")
      r.fail(
        "This PDF uses a layer panel filter that cannot be preserved yet.",
      );
  }
  const set = new Set(groups.map((g) => r.dict(g)));
  const objectRefs = new Map(
    doc.context
      .enumerateIndirectObjects()
      .map(([ref, object]) => [object, ref]),
  );
  let reconstructed = false;
  if (set.size !== groups.length)
    r.fail("This PDF repeats a layer identity in its layer catalog.");
  const group = (g: PDFObject) => {
    if (!set.has(r.dict(g)))
      r.fail("A layer reference is missing from this PDF's layer catalog.");
  };
  function expression(v: PDFObject, depth = 0) {
    if (depth > 100) r.fail("This PDF's layer expression is too complex.");
    if (r.resolve(v) instanceof PDFDict) {
      group(v);
      return;
    }
    const a = r.array(v),
      op = r.name(a[0]);
    if (
      !["And", "Or", "Not"].includes(op) ||
      a.length < 2 ||
      (op === "Not" && a.length !== 2)
    )
      r.fail("This PDF has an invalid layer visibility expression.");
    a.slice(1).forEach((x) => expression(x, depth + 1));
  }
  const visited = new Set<PDFObject>();
  function visit(value: PDFObject, depth = 0) {
    const obj = r.resolve(value);
    if (!obj || visited.has(obj)) return;
    if (depth > 200 || visited.size > 100000)
      r.fail("This PDF's layer graph is too complex.");
    visited.add(obj);
    if (obj instanceof PDFArray) {
      obj.asArray().forEach((v) => visit(v, depth + 1));
      return;
    }
    if (obj instanceof PDFStream) {
      visit(obj.dict, depth + 1);
      return;
    }
    if (!(obj instanceof PDFDict)) return;
    if (r.name(obj.get(key("Type"))) === "OCG") {
      if (!raw && !set.has(obj)) {
        // With no document configuration, consumers ignore optional content.
        // Only a plain named group can safely acquire an explicit visible
        // default. Usage rules, intents and membership expressions must not
        // be guessed. Keep original group identity through the page copier.
        r.keys(obj, ["Type", "Name"]);
        const ref = objectRefs.get(obj);
        if (!ref)
          r.fail("An unconfigured layer has no stable object identity.");
        groups.push(ref!);
        set.add(obj);
        reconstructed = true;
      }
      // Preserve an existing unregistered page group as unregistered. Do not
      // invent visibility settings or add it to another input's layer catalog.
      // Configuration references still require registered groups below.
      if (!set.has(obj)) {
        r.keys(obj, ["Type", "Name", "Intent", "Usage"]);
        const title = r.resolve(obj.get(key("Name")));
        if (!(title instanceof PDFString || title instanceof PDFHexString))
          r.fail("An unregistered layer has no name.");
      }
    }
    if (r.name(obj.get(key("Type"))) === "OCMD") {
      if (!raw)
        r.fail(
          "Unconfigured layer expressions cannot be reconstructed safely.",
        );
      r.keys(obj, ["Type", "OCGs", "P", "VE"]);
      const g = obj.get(key("OCGs"));
      if (g)
        (r.resolve(g) instanceof PDFArray ? r.array(g) : [g]).forEach(group);
      const policy = r.name(obj.get(key("P")));
      if (policy && !["AllOn", "AnyOn", "AnyOff", "AllOff"].includes(policy))
        r.fail("This PDF has an unsupported layer membership policy.");
      const ve = obj.get(key("VE"));
      if (ve) expression(ve);
      if (!g && !ve)
        r.fail("This PDF has an incomplete layer membership dictionary.");
    }
    for (const [, v] of obj.entries()) visit(v, depth + 1);
  }
  // Only reachable optional-content groups can affect the document. Older saved
  // revisions may leave unused groups in the object table.
  visit(doc.catalog);
  for (const g of groups) {
    const d = r.dict(g);
    r.keys(d, ["Type", "Name", "Intent", "Usage"]);
    if (r.name(d.get(key("Type"))) !== "OCG")
      r.fail("This PDF has an invalid layer group.");
    const title = r.resolve(d.get(key("Name")));
    if (!(title instanceof PDFString || title instanceof PDFHexString))
      r.fail("This PDF has an unnamed layer.");
  }
  if (!config && reconstructed)
    config = doc.context.obj({ BaseState: "ON", ON: groups, Order: [] });
  if (!config) return undefined;
  for (const n of ["ON", "OFF", "Locked"]) {
    const a = config.get(key(n));
    if (a) r.array(a).forEach(group);
  }
  const on = config.get(key("ON")) ? r.array(config.get(key("ON"))) : [];
  const off = config.get(key("OFF")) ? r.array(config.get(key("OFF"))) : [];
  if (on.some((g) => off.some((h) => r.resolve(g) === r.resolve(h))))
    r.fail("This PDF gives a layer conflicting visibility states.");
  const rb = config.get(key("RBGroups"));
  if (rb) r.array(rb).forEach((a) => r.array(a).forEach(group));
  const auto = config.get(key("AS"));
  if (auto)
    r.array(auto).forEach((v) => {
      const d = r.dict(v);
      r.keys(d, ["Event", "OCGs", "Category"]);
      if (!["View", "Print", "Export"].includes(r.name(d.get(key("Event")))))
        r.fail("This PDF has an unsupported automatic layer event.");
      const g = d.get(key("OCGs"));
      if (g) r.array(g).forEach(group);
      r.array(d.get(key("Category"))).forEach((c) => {
        if (
          !["Zoom", "View", "Print", "Export", "User", "Language"].includes(
            r.name(c),
          )
        )
          r.fail("This PDF has an unsupported layer usage category.");
      });
    });
  function order(v: PDFObject, depth = 0) {
    if (depth > 100) r.fail("Layer order is too complex.");
    const x = r.resolve(v);
    if (x instanceof PDFString || x instanceof PDFHexString) return;
    if (x instanceof PDFArray) x.asArray().forEach((y) => order(y, depth + 1));
    else group(v);
  }
  const orderValue = config.get(key("Order"));
  if (orderValue) r.array(orderValue).forEach((v) => order(v));
  const enabled = groups.filter((g) =>
    off.some((h) => r.resolve(g) === r.resolve(h))
      ? false
      : on.some((h) => r.resolve(g) === r.resolve(h)) ||
        r.name(config!.get(key("BaseState"))) !== "OFF",
  );
  return { groups, config, enabled, reconstructed };
}
export function copyLayers(
  plan: ReturnType<typeof inspectLayers>,
  copier: PDFObjectCopier,
) {
  if (!plan) return undefined;
  const groups = plan.groups.map((g) => copier.copy(g)),
    config = copier.copy(plan.config);
  const auto = config.lookupMaybe(key("AS"), PDFArray);
  if (auto)
    for (const v of auto.asArray()) {
      const d = config.context.lookup(v, PDFDict);
      if (!d.has(key("OCGs"))) d.set(key("OCGs"), config.context.obj(groups));
    }
  return { groups, enabled: plan.enabled.map((g) => copier.copy(g)), config };
}
export function finishLayers(
  doc: PDFDocument,
  parts: ReturnType<typeof copyLayers>[],
) {
  const layers = parts.filter((p) => !!p);
  if (!layers.length) return;
  const all = layers.flatMap((p) => p.groups),
    on = layers.flatMap((p) => p.enabled);
  const array = (d: PDFDict, n: string) =>
    d.has(key(n)) ? doc.context.lookup(d.get(key(n)), PDFArray).asArray() : [];
  // Explicit per-group states prevent one input's BaseState from changing another.
  const config = doc.context.obj({
    BaseState: "ON",
    ON: on,
    OFF: all.filter((g) => !on.includes(g)),
    Intent: "View",
    ListMode: "AllPages",
  });
  const order = layers.flatMap((p, i) => {
    const entries = array(p.config, "Order");
    if (!entries.length) return [];
    const title =
      p.config.get(key("Name")) || PDFString.of(`Document ${i + 1}`);
    // Keep each input's original hierarchy inside its own named panel group.
    return [doc.context.obj([title, doc.context.obj(entries)])];
  });
  if (order.length) config.set(key("Order"), doc.context.obj(order));
  for (const n of ["RBGroups", "Locked", "AS"]) {
    const values = layers.flatMap((p) => array(p.config, n));
    if (values.length) config.set(key(n), doc.context.obj(values));
  }
  doc.catalog.set(
    key("OCProperties"),
    doc.context.obj({ OCGs: all, D: config }),
  );
}
