type ModuleMap = Record<string, { file: string; css: string[] }>;
let mapRequest: Promise<ModuleMap> | null = null;
function resourceMap(signal?: AbortSignal): Promise<ModuleMap> {
  if (mapRequest) return mapRequest;
  const script = document.querySelector<HTMLScriptElement>(
    'script[type="module"][src*="/assets/index-"]',
  );
  const entry = script && new URL(script.src).pathname.split("/").pop();
  if (!entry || !/^index-[\w-]+\.js$/.test(entry))
    return Promise.reject(
      new Error("This tool could not reload. Please reopen the page."),
    );
  mapRequest = fetch(`/module-map-${entry.replace(/\.js$/, "")}.json`, {
    signal,
  })
    .then(async (response) => {
      if (!response.ok) throw new Error("Tool retry resources could not load.");
      return (await response.json()) as ModuleMap;
    })
    .catch((error: unknown) => {
      mapRequest = null;
      throw error;
    });
  return mapRequest;
}
const safeAsset = (path: string) =>
  /^\/assets\/[\w.-]+\.(?:js|mjs|css)$/.test(path);
async function styles(paths: string[], attempt: number, signal?: AbortSignal) {
  await Promise.all(
    paths.map((path) => {
      if (!safeAsset(path)) throw new Error("Invalid local tool resource");
      if (
        Array.from(
          document.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"]'),
        ).some((link) => new URL(link.href).pathname === path && link.sheet)
      )
        return;
      return new Promise<void>((resolve, reject) => {
        const link = document.createElement("link");
        const cleanup = () => signal?.removeEventListener("abort", abort);
        const fail = () => {
          cleanup();
          link.remove();
          reject(new Error("Tool styles could not load."));
        };
        const abort = () => fail();
        if (signal?.aborted) {
          fail();
          return;
        }
        link.rel = "stylesheet";
        link.href = `${path}?retry=${attempt}`;
        link.onload = () => {
          cleanup();
          resolve();
        };
        link.onerror = fail;
        signal?.addEventListener("abort", abort, { once: true });
        document.head.append(link);
      });
    }),
  );
}
/** Retry only this release's static code; selected documents stay in memory. */
export async function loadModule<T>(
  key: string,
  normal: () => Promise<T>,
  attempt: number,
  signal?: AbortSignal,
): Promise<T> {
  try {
    const module = await normal();
    if (attempt > 0) {
      const map = await resourceMap(signal);
      if (map[key]) await styles(map[key].css, attempt, signal);
    }
    return module;
  } catch (error) {
    if (!attempt || signal?.aborted) throw error;
    const map = await resourceMap(signal);
    const item = map[key];
    if (!item || !safeAsset(item.file)) throw error;
    await styles(item.css, attempt, signal);
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    return (await import(
      /* @vite-ignore */ `${item.file}?retry=${attempt}`
    )) as T;
  }
}
