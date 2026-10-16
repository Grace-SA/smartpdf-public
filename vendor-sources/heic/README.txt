SmartWorks HEIC decoder source and rebuilding record, 2026-10-08

Browser dependency: libheif-js 1.23.5 (LGPL-3.0), unmodified upstream module.
npm gitHead: d8ec4bc3bc5bf8055975577bccbbc7e1d7313c2d
WASM release: catdad-experiments/libheif-emscripten v1.23.5
libheif submodule: 413e2a87e6a70b3eccc3a3adc5801179dd2d9e00
libde265 default in pinned build script: 1.0.15 (LGPL-3.0).
Emscripten version in upstream workflow: 3.1.61.
Archive filenames include versions/commits; corresponding source is provided
alongside this notice. The pinned upstream build script and CI recipe are included.
No decoder-library source modifications were made by SmartWorks.

Rebuild the library with the upstream recipes, then use libheif-js scripts/install.js
with the generated libheif.tar.gz. Replace node_modules/libheif-js with that build
and rebuild SmartWorks with its normal Vite build. The integration source is
src/photos/heic.worker.ts, heic.ts, heic-header.ts and heic-color.ts in the supplied
SmartWorks development workspace; TypeScript wrappers do not change the library.
Application object/source and build files must accompany any later distributed
release so recipients can relink a modified library. No public deployment is
performed by this change. Public-release packaging/licensing review remains a
release gate; an npm license label is not an HEVC patent license.

Upstream references:
https://github.com/catdad-experiments/libheif-js
https://github.com/catdad-experiments/libheif-emscripten/tree/v1.23.5
https://github.com/strukturag/libheif/tree/413e2a87e6a70b3eccc3a3adc5801179dd2d9e00
https://github.com/strukturag/libde265/tree/v1.0.15
