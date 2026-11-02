import { useEffect, useState } from "react";
import { loadModule } from "../platform/module-loading";

export function WordEntry() {
  const [module, setModule] = useState<typeof import("./WordPage")>();
  const [attempt, setAttempt] = useState(0);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void loadModule(
      "word",
      () => import("./WordPage"),
      attempt,
      controller.signal,
    )
      .then((value) => {
        if (!controller.signal.aborted) setModule(value);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [attempt]);
  if (module) return <module.WordPage />;
  return failed ? (
    <main>
      <h1>Word to PDF</h1>
      <p>This tool could not open. Try again; no document has been uploaded.</p>
      <button
        onClick={() => {
          setFailed(false);
          setAttempt((value) => value + 1);
        }}
      >
        Retry opening Word to PDF
      </button>
    </main>
  ) : (
    <p role="status">Opening Word to PDF…</p>
  );
}
