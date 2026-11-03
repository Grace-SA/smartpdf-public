/** Scope this adapter to the private one-shot Worker. The pinned Emscripten
 * runtime grows its heap through this native JS method; other tools are untouched. */
export function limitWasmHeap(limit = 192 * 1024 * 1024) {
  const prototype = WebAssembly.Memory.prototype,
    nativeGrow = prototype.grow;
  let exhausted = false;
  prototype.grow = function (this: WebAssembly.Memory, pages: number) {
    if (this.buffer.byteLength + pages * 65536 > limit) {
      exhausted = true;
      throw new RangeError("Local memory limit");
    }
    const previous = nativeGrow.call(this, pages);
    exhausted = false;
    return previous;
  };
  return {
    exhausted: () => exhausted,
    restore: () => {
      prototype.grow = nativeGrow;
    },
  };
}
