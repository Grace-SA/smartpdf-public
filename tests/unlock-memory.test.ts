import { test, expect } from "vitest";
import { limitWasmHeap } from "../src/unlock/memory";
test("private WASM growth cannot cross its ceiling and the native API is restored", () => {
  const guard = limitWasmHeap(2 * 65536),
    memory = new WebAssembly.Memory({ initial: 1 });
  try {
    expect(memory.grow(1)).toBe(1);
    expect(() => memory.grow(1)).toThrow(RangeError);
    expect(memory.buffer.byteLength).toBe(2 * 65536);
    expect(guard.exhausted()).toBe(true);
  } finally {
    guard.restore();
  }
  expect(memory.grow(1)).toBe(2);
});
test("a rejected speculative allocation does not misclassify a successful smaller fallback", () => {
  const guard = limitWasmHeap(3 * 65536),
    memory = new WebAssembly.Memory({ initial: 1 });
  try {
    expect(() => memory.grow(4)).toThrow(RangeError);
    expect(guard.exhausted()).toBe(true);
    expect(memory.grow(1)).toBe(1);
    expect(guard.exhausted()).toBe(false);
  } finally {
    guard.restore();
  }
});
