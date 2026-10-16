// Synthetic-only diagnostic, loaded inside the app's realm before disconnecting.
const engineUrl = new URL(import.meta.url).searchParams.get("engine");
if (!/^\/assets\/engine-[\w-]+\.js$/.test(engineUrl))
  throw new Error("Unexpected diagnostic module");
const { Engine, renderPage } = await import(engineUrl);
const engine = new Engine();
await engine.prepare();
window.m0Diagnose = async (file) => {
  let preview;
  let stage = "open";
  const controller = new window.AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const signal = controller.signal;
    preview = await engine.open(file, signal, (value) => {
      stage = value;
    });
    stage = "renderPage";
    const rendered = await renderPage(preview, 1, signal);
    rendered.canvas.width = 0;
    rendered.canvas.height = 0;
    return { stage, result: "passed" };
  } catch (error) {
    return {
      stage,
      name: error.name,
      message: String(error.message).slice(0, 600),
      stack: String(error.stack).slice(0, 2000),
    };
  } finally {
    clearTimeout(timer);
    await preview?.dispose();
    engine.dispose();
  }
};
window.m0DisposeDiagnostic = () => engine.dispose();

// Constructors and event data must remain in the app realm on older WebKit.
window.m0InstallDiagnostics = (record, shouldDelay) => {
  const w = window;
  const OriginalWorker = window.Worker;
  const OriginalReader = window.FileReader;
  const originalFrame = window.requestAnimationFrame;
  window.requestAnimationFrame = (callback) => {
    const start = performance.now();
    return originalFrame.call(window, (timestamp) => {
      record("animation frame wait ms", performance.now() - start);
      callback(timestamp);
    });
  };
  w.Worker = class extends OriginalWorker {
    constructor(url, options) {
      try {
        super(url, options);
        record("worker created", options?.type ?? "classic");
      } catch (error) {
        record("worker constructor failed", `${error.name}: ${error.message}`);
        throw error;
      }
      this.addEventListener("error", (event) =>
        record("worker error", event.message),
      );
      this.addEventListener("message", (event) => {
        const data = event.data;
        if (data?.ready) record("probe ready", true);
        if (data?.result?.ok === true) record("probe passed", true);
        if (data?.reason) record("worker reply", JSON.stringify(data.reason));
        if (data?.result?.ok === false)
          record("probe result", JSON.stringify(data.result));
      });
    }
    postMessage(...args) {
      try {
        super.postMessage(...args);
      } catch (error) {
        record("worker send failed", `${error.name}: ${error.message}`);
        throw error;
      }
    }
  };
  w.FileReader = class extends OriginalReader {
    constructor() {
      super();
      this.addEventListener("error", () =>
        record("file read", this.error?.name),
      );
      this.addEventListener("load", () =>
        record(
          "file read",
          `bytes=${this.result?.byteLength}; sameRealm=${this.result instanceof w.ArrayBuffer}`,
        ),
      );
    }
    readAsArrayBuffer(blob) {
      if (shouldDelay())
        this.readTimer = setTimeout(() => super.readAsArrayBuffer(blob), 1500);
      else super.readAsArrayBuffer(blob);
    }
    abort() {
      clearTimeout(this.readTimer);
      super.abort();
    }
  };
  return () => {
    window.Worker = OriginalWorker;
    window.FileReader = OriginalReader;
    window.requestAnimationFrame = originalFrame;
  };
};
