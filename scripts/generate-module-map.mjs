import { readFile, writeFile } from "node:fs/promises";
import { basename } from "node:path";

const outputDirectory = process.argv[2] || "dist";
const manifest = JSON.parse(
  await readFile(`${outputDirectory}/.vite/manifest.json`, "utf8"),
);
const entry = Object.values(manifest).find((item) => item.isEntry);
if (!entry) throw new Error("Missing main build entry");
const sources = {
  ...(process.env.VITE_ENABLE_EXCEL === "true"
    ? { excel: "src/excel/ExcelPage.tsx" }
    : {}),
  word: "src/word/WordPage.tsx",
  ...(process.env.VITE_ENABLE_PROTECT === "true"
    ? { protect: "src/protect/ProtectPanel.tsx" }
    : {}),
  unlock: "src/unlock/UnlockPanel.tsx",
  numbers: "src/numbers/NumberPanel.tsx",
  watermark: "src/watermark/WatermarkPanel.tsx",
  raster: "src/raster/RasterPanel.tsx",
  engine: "src/platform/engine.ts",
  merge: "src/combine/CombinePanel.tsx",
  photoService: "src/photos/service.ts",
  compressService: "src/compress/service.ts",
  photos: "src/photos/PhotoPanel.tsx",
  sign: "src/sign/SignPanel.tsx",
  compress: "src/compress/CompressPanel.tsx",
  split: "src/split/SplitPanel.tsx",
  organize: "src/organize/OrganizePanel.tsx",
  rotate: "src/rotate/RotatePanel.tsx",
};
const cssFor = (key, visited = new Set()) => {
  if (visited.has(key)) return [];
  visited.add(key);
  const item = manifest[key];
  return [
    ...(item?.css ?? []),
    ...(item?.imports ?? []).flatMap((dependency) =>
      cssFor(dependency, visited),
    ),
  ];
};
const map = Object.fromEntries(
  Object.entries(sources).map(([name, source]) => {
    const item = manifest[source];
    if (!item?.file) throw new Error(`Missing retry module: ${source}`);
    return [
      name,
      {
        file: "/" + item.file,
        css: [...new Set(cssFor(source))].map((file) => "/" + file),
      },
    ];
  }),
);
await writeFile(
  `${outputDirectory}/module-map-${basename(entry.file, ".js")}.json`,
  JSON.stringify(map),
);
console.log("Generated version-specific module retry map");
