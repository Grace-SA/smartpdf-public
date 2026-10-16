// Windows restricted environments may deny native realpath on pnpm junctions.
// Fall back to Node's standard path resolver, which uses the same permissions.
const fs = require("node:fs");
const nativeRealpath = fs.realpathSync.native;
fs.realpathSync.native = function (path, options) {
  try {
    return nativeRealpath(path, options);
  } catch (error) {
    if (process.platform !== "win32" || error.code !== "EPERM") throw error;
    return fs.realpathSync(path, options);
  }
};
