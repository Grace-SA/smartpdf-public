import {
  readdir,
  readFile,
  writeFile,
  mkdir,
  copyFile,
} from "node:fs/promises";
import { join, dirname } from "node:path";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const root = dirname(require.resolve("pdfjs-dist/package.json"));
const pack = {};
await mkdir("public/notices", { recursive: true });
await copyFile(
  "node_modules/@neslinesli93/qpdf-wasm/dist/qpdf.wasm",
  "public/qpdf.wasm",
);
await copyFile(
  "vendor-licenses/qpdf-wasm-ISC.txt",
  "public/notices/qpdf-wasm-ISC.txt",
);
await copyFile(
  "node_modules/pdfjs-dist/LICENSE",
  "public/notices/qpdf-Apache-2.0.txt",
);
await copyFile(
  "vendor-licenses/qpdf-12.2.0-NOTICE.txt",
  "public/notices/qpdf-12.2.0-NOTICE.txt",
);
// PDF.js legacy bundles core-js; it is not a separate package.json dependency.
await copyFile(
  "vendor-licenses/core-js-3.50.0-LICENSE.txt",
  "public/notices/core-js-3.50.0-LICENSE.txt",
);
for (const [folder, kind] of [
  ["cmaps", "cMapUrl"],
  ["standard_fonts", "standardFontDataUrl"],
  ["wasm", "wasmUrl"],
  ["iccs", "iccUrl"],
]) {
  for (const file of await readdir(join(root, folder))) {
    if (/LICENSE|NOTICE/i.test(file)) {
      await copyFile(
        join(root, folder, file),
        join("public/notices", `pdfjs-${folder}-${file}.txt`),
      );
    } else if (
      /\.(bcmap|ttf|pfb|wasm|js|icc)$/.test(file) &&
      !file.startsWith("quickjs")
    ) {
      pack[`${kind}/${file}`] = (
        await readFile(join(root, folder, file))
      ).toString("base64");
    }
  }
}
for (const [pkg, license] of [
  ["pdfjs-dist", "LICENSE"],
  ["pdf-lib", "LICENSE.md"],
  ["react", "LICENSE"],
  ["react-dom", "LICENSE"],
  ["fast-xml-parser", "LICENSE"],
  ["libheif-js", "LICENSE"],
]) {
  const path = join("node_modules", pkg);
  await copyFile(join(path, license), `public/notices/${pkg}.txt`);
}
const licenses = JSON.parse(
  await readFile("docs/dependency-licenses.json", "utf8"),
);
await copyFile(
  "vendor-licenses/pako-1.0.11-LICENSE.txt",
  "public/notices/pako-1.0.11-LICENSE.txt",
);
if (licenses.error)
  throw new Error("Dependency license inventory is unavailable");
for (const entries of Object.values(licenses)) {
  for (const pkg of entries) {
    // Native optional Node canvas is never distributed in the browser build.
    if (pkg.name.startsWith("@napi-rs/")) continue;
    const prefix = `${pkg.name.replace("/", "+")}@${pkg.versions[0]}`;
    const packageFolder = (await readdir("node_modules/.pnpm")).find(
      (dir) => dir === prefix || dir.startsWith(`${prefix}_`),
    );
    if (!packageFolder)
      throw new Error(`Installed package not found: ${pkg.name}`);
    const folder = join(
      "node_modules/.pnpm",
      packageFolder,
      "node_modules",
      pkg.name,
    );
    const files = (await readdir(folder)).filter((file) =>
      /^(license|notice|copying)/i.test(file),
    );
    if (pkg.name === "@nodable/entities" && !files.length) {
      await copyFile(
        "vendor-licenses/nodable-entities-LICENSE.txt",
        "public/notices/nodable-entities-LICENSE.txt",
      );
      continue;
    }
    if (pkg.name === "@neslinesli93/qpdf-wasm" && !files.length) {
      await copyFile(
        "vendor-licenses/qpdf-wasm-ISC.txt",
        "public/notices/qpdf-wasm-ISC.txt",
      );
      continue;
    }
    if (pkg.name === "@pdf-lib/fontkit" && !files.length) {
      await copyFile(
        "vendor-licenses/pdf-lib-fontkit-MIT.txt",
        "public/notices/pdf-lib-fontkit-MIT.txt",
      );
      await copyFile(
        "vendor-licenses/pdf-lib-fontkit-NOTICE.txt",
        "public/notices/pdf-lib-fontkit-NOTICE.txt",
      );
      continue;
    }
    if (!files.length) throw new Error(`Missing license file: ${pkg.name}`);
    for (const file of files)
      await copyFile(
        join(folder, file),
        `public/notices/${pkg.name.replace(/[@/]/g, "_")}-${file}.txt`,
      );
  }
}
await writeFile("public/pdf-resources.json", JSON.stringify(pack));
await copyFile(
  "node_modules/libheif-js/libheif-wasm/LICENSE",
  "public/notices/libheif-full-LICENSE.txt",
);
await copyFile(
  "vendor-licenses/libde265-1.0.15-COPYING.txt",
  "public/notices/libde265-COPYING.txt",
);
await mkdir("public/notices/heic-source", { recursive: true });
for (const file of await readdir("vendor-sources/heic"))
  await copyFile(
    join("vendor-sources/heic", file),
    join("public/notices/heic-source", file),
  );
await writeFile(
  "public/notices/heic-source/index.html",
  `<!doctype html><meta charset="utf-8"><title>HEIC source</title><h1>HEIC decoder source and rebuild instructions</h1><ul>${(await readdir("vendor-sources/heic")).map((file) => `<li><a href="./${file}">${file}</a></li>`).join("")}</ul>`,
);
await writeFile(
  "public/notices/pdf-lib-modifications.txt",
  "SmartWorks uses pdf-lib 1.17.1 (MIT), with local resource guards in the ESM and CommonJS distributions. Changes bound decode buffers, cumulative decoder allocation, parser nesting, object count and object-stream headers, propagate resource-limit failures, and detect conflicting duplicate dictionary keys so transformations can reject ambiguous inputs. The original copyright and license are preserved in pdf-lib.txt. Reproducible patch: patches/pdf-lib@1.17.1.patch in the SmartWorks source distribution. These limits are not a total browser-memory guarantee.\n",
);
for (const file of await readdir("public/sign-fonts")) {
  if (file.endsWith("OFL.txt"))
    await copyFile(
      join("public/sign-fonts", file),
      join("public/notices", file),
    );
}
await copyFile(
  "public/watermark-fonts/OFL.txt",
  "public/notices/watermark-font-OFL.txt",
);
await writeFile(
  "public/notices/watermark-font-modifications.txt",
  "Smart PDF Sans Regular is derived from Google Fonts Noto Sans SC at commit 2894aab31764f10f29c421bdfd2340d3b382d384. The weight axis is fixed at 400 with fontTools and family/style names are changed to Smart PDF Sans Regular. Glyph data is padded to four bytes for compatible TrueType subsetting. Original copyright and SIL Open Font License 1.1 are preserved in watermark-font-OFL.txt. PDF output embeds only required glyphs. This font is served from this site; no external font request is made at runtime.\n",
);
const links = (await readdir("public/notices"))
  .map((file) => `<li><a href="./${file}">${file}</a></li>`)
  .join("");
await writeFile(
  "public/notices/index.html",
  `<!doctype html><html lang="en"><meta charset="utf-8"><title>Third-party notices</title><h1>Third-party notices</h1><ul>${links}</ul></html>`,
);
console.log(`Prepared ${Object.keys(pack).length} local binary resources.`);
