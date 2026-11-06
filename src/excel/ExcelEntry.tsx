import { useEffect, useState } from "react";
import { loadModule } from "../platform/module-loading";

export function ExcelEntry() {
  const [module, setModule] = useState<typeof import("./ExcelPage")>();
  const [attempt, setAttempt] = useState(0);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void loadModule(
      "excel",
      () => import("./ExcelPage"),
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
  if (module) return <module.ExcelPage />;
  return failed ? (
    <main>
      <h1>Excel to PDF</h1>
      <p>This tool could not open. Try again; no document has been uploaded.</p>
      <button
        onClick={() => {
          setFailed(false);
          setAttempt((value) => value + 1);
        }}
      >
        Retry opening Excel to PDF
      </button>
    </main>
  ) : (
    <p role="status">Opening Excel to PDF…</p>
  );
}
