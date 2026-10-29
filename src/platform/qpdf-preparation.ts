/** Cache only public engine bytes. Each consumer owns its cancellation scope. */
export function qpdfPreparation(
  failure: (reason: "cancelled" | "engine") => Error,
) {
  let cached: Promise<Uint8Array<ArrayBuffer>> | null = null;
  return function prepare(
    signal: AbortSignal,
  ): Promise<Uint8Array<ArrayBuffer>> {
    if (signal.aborted) return Promise.reject(failure("cancelled"));
    if (cached) return cached;
    const controller = new AbortController(),
      abort = () => controller.abort();
    signal.addEventListener("abort", abort, { once: true });
    const timer = setTimeout(() => controller.abort(), 30000);
    const request = Promise.resolve()
      .then(() =>
        fetch("/qpdf.wasm", { signal: controller.signal, credentials: "omit" }),
      )
      .then(async (response) => {
        if (!response.ok) throw failure("engine");
        if (
          Number(response.headers.get("content-length") || 0) >
          8 * 1024 * 1024
        )
          throw failure("engine");
        const bytes = new Uint8Array(await response.arrayBuffer());
        if (bytes.length > 8 * 1024 * 1024 || !WebAssembly.validate(bytes))
          throw failure("engine");
        return bytes;
      })
      .catch(() => {
        if (cached === request) cached = null;
        throw failure(signal.aborted ? "cancelled" : "engine");
      })
      .finally(() => {
        clearTimeout(timer);
        signal.removeEventListener("abort", abort);
      });
    cached = request;
    return request;
  };
}
