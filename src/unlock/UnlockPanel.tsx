import {
  forwardRef,
  useEffect,
  useEffectEvent,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { unlockOperation, prepareUnlock } from "./service";
import {
  UnlockFailure,
  unlockMessages,
  type UnlockReason,
  type UnlockStatus,
  validatePassword,
} from "./model";
import { LeaveTaskDialog } from "../LeaveTaskDialog";
import { ConfirmDialog } from "../ConfirmDialog";
import { TaskNotice } from "../TaskNotice";
import { ToolIcon } from "../ToolIcon";
import { safeFilename } from "../photos/model";
import { track } from "../analytics";
import "./unlock.css";
export { prepareUnlock };
export type UnlockHandle = { guard: (action: () => void) => void };
export const UnlockPanel = forwardRef<
  UnlockHandle,
  {
    seed: File[];
    consume: (files: File[]) => void;
    pause: boolean;
    publish: (file: File, pages: number) => void;
    replace: () => void;
    onDirty: (dirty: boolean) => void;
    onBusy: (busy: boolean) => void;
  }
>(function UnlockPanel(
  { seed, consume, pause, publish, replace, onDirty, onBusy },
  ref,
) {
  const [file] = useState(() => seed[0]!);
  const [status, setStatus] = useState<UnlockStatus | null>(null);
  const [reason, setReason] = useState<UnlockReason | null>(null);
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [working, setWorking] = useState<"inspect" | "unlock" | null>(null);
  const [stage, setStage] = useState("Unlocking your PDF…");
  const [ordinary, setOrdinary] = useState(false);
  const [pending, setPending] = useState<{ action: () => void } | null>(null);
  const controller = useRef<AbortController | null>(null),
    alive = useRef(true),
    input = useRef<HTMLInputElement>(null);
  useImperativeHandle(
    ref,
    () => ({
      guard(action) {
        if (controller.current) return;
        setPending({ action });
      },
    }),
    [],
  );
  useEffect(
    () => () => {
      alive.current = false;
      controller.current?.abort();
      if (input.current) input.current.value = "";
      onDirty(false);
      onBusy(false);
    },
    [onDirty, onBusy],
  );
  const cancel = () => {
    setPassword("");
    controller.current?.abort();
  };
  async function inspect() {
    if (controller.current) return;
    const job = new AbortController();
    controller.current = job;
    setWorking("inspect");
    setReason(null);
    onBusy(true);
    onDirty(true);
    try {
      const result = await unlockOperation(
        file,
        { kind: "inspect" },
        job.signal,
      );
      if (alive.current && "status" in result) setStatus(result.status);
    } catch (error) {
      if (alive.current)
        setReason(error instanceof UnlockFailure ? error.reason : "engine");
    } finally {
      if (controller.current === job) controller.current = null;
      if (alive.current) {
        setWorking(null);
        onBusy(false);
      }
    }
  }
  const startSeed = useEffectEvent((files: File[]) => {
    consume(files);
    void inspect();
  });
  useEffect(() => {
    if (seed.length && !pause) startSeed(seed);
  }, [seed, pause]);
  async function unlock(allowOrdinary = false) {
    if (controller.current || !status || status === "not-encrypted") return;
    try {
      validatePassword(password);
    } catch {
      setReason("password-format");
      return;
    }
    const job = new AbortController();
    controller.current = job;
    setWorking("unlock");
    setReason(null);
    setOrdinary(false);
    onBusy(true);
    setStage("Unlocking your PDF…");
    const started = performance.now();
    track("process_start", "unlock", { fileCount: 1, totalBytes: file.size });
    try {
      const result = await unlockOperation(
        file,
        { kind: "unlock", password, ordinary: allowOrdinary },
        job.signal,
        (next) => {
          if (
            alive.current &&
            !job.signal.aborted &&
            controller.current === job
          )
            setStage(
              next === "unlock"
                ? "Unlocking your PDF…"
                : "Checking your unlocked PDF…",
            );
        },
      );
      if (!alive.current || job.signal.aborted) return;
      if (!("bytes" in result)) {
        setStatus(result.status);
        return;
      }
      const output = new File(
        [result.bytes],
        safeFilename(file.name.replace(/\.pdf$/i, "") + "-unlocked.pdf"),
        { type: "application/pdf" },
      );
      setPassword("");
      if (input.current) input.current.value = "";
      track("process_success", "unlock", {
        fileCount: 1,
        totalBytes: file.size,
        pages: result.pages,
        durationMs: performance.now() - started,
      });
      publish(output, result.pages);
    } catch (error) {
      const failure = error instanceof UnlockFailure ? error.reason : "engine";
      if (failure !== "standard")
        track(
          failure === "cancelled" ? "process_cancel" : "process_failure",
          "unlock",
          {
            reason:
              failure === "cancelled"
                ? "cancelled"
                : failure === "timeout"
                  ? "timeout"
                  : failure === "resource"
                    ? "resource_limit"
                    : failure === "unsupported" || failure === "signature"
                      ? "unsupported"
                      : "validation",
          },
        );
      if (alive.current) {
        setReason(failure);
        if (failure === "standard") setOrdinary(true);
        if (
          [
            "unsupported",
            "signature",
            "invalid",
            "resource",
            "validation",
          ].includes(failure)
        ) {
          setStatus(null);
          setPassword("");
        }
      }
    } finally {
      if (controller.current === job) controller.current = null;
      if (alive.current) {
        setWorking(null);
        onBusy(false);
      }
    }
  }
  const canRetry =
    reason === "engine" || reason === "timeout" || reason === "cancelled";
  return (
    <section className="unlock-task" aria-label="Unlock PDF">
      {pending && (
        <LeaveTaskDialog
          description="Your selected PDF and password will be cleared."
          keep={() => setPending(null)}
          leave={() => {
            const action = pending.action;
            setPassword("");
            setPending(null);
            action();
          }}
        />
      )}
      {ordinary && (
        <ConfirmDialog
          title="Create an ordinary PDF copy"
          cancelLabel="Keep this task"
          onCancel={() => setOrdinary(false)}
          action={
            <button onClick={() => void unlock(true)}>
              Create ordinary unlocked PDF
            </button>
          }
        >
          <p>
            The new PDF will not retain PDF/A, PDF/X or PDF/UA compliance
            declarations. Page content, supported structure and colour settings
            will be retained. Your original stays unchanged.
          </p>
        </ConfirmDialog>
      )}
      {working === "unlock" && (
        <TaskNotice
          working
          message={stage}
          title="Unlocking your PDF…"
          close={cancel}
        />
      )}
      <div className="unlock-file">
        <span className="tool-icon icon-unlock">
          <ToolIcon tool="unlock" />
        </span>
        <div>
          <strong>{file.name}</strong>
          <span>
            {file.size < 1024 * 1024
              ? `${Math.max(1, Math.round(file.size / 1024))} KB`
              : `${(file.size / 1024 / 1024).toFixed(1)} MB`}
          </span>
        </div>
        <button
          className="secondary"
          disabled={!!working}
          onClick={() => {
            setPassword("");
            replace();
          }}
        >
          Choose another file
        </button>
      </div>
      {working === "inspect" ? (
        <div className="unlock-check">
          <p role="status">Checking this PDF…</p>
          <button className="secondary" onClick={cancel}>
            Cancel checking
          </button>
        </div>
      ) : (
        <>
          {status === "not-encrypted" ? (
            <div className="unlock-info">
              <h2>No unlocking needed</h2>
              <p>
                This PDF isn't password-protected. Choose another file to
                unlock.
              </p>
            </div>
          ) : (
            status && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void unlock();
                }}
              >
                <h2>
                  {status === "accessible"
                    ? "Remove PDF protection"
                    : "Enter the PDF password"}
                </h2>
                {status === "accessible" ? (
                  <p>
                    This PDF opens without a password. Remove its remaining
                    protection.
                  </p>
                ) : (
                  <>
                    <label htmlFor="unlock-password">PDF password</label>
                    <div className="unlock-password">
                      <input
                        ref={input}
                        id="unlock-password"
                        type={visible ? "text" : "password"}
                        value={password}
                        autoComplete="off"
                        autoCapitalize="none"
                        spellCheck={false}
                        required
                        aria-invalid={
                          reason === "password" || reason === "password-format"
                        }
                        aria-describedby={reason ? "unlock-error" : undefined}
                        onChange={(e) => {
                          setPassword(e.target.value);
                          setReason(null);
                        }}
                      />
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => {
                          setVisible((v) => !v);
                          input.current?.focus({ preventScroll: true });
                        }}
                      >
                        {visible ? "Hide password" : "Show password"}
                      </button>
                    </div>
                  </>
                )}
                {reason && (
                  <p className="unlock-error" id="unlock-error" role="alert">
                    {unlockMessages[reason]}
                  </p>
                )}
                <button
                  className="unlock-primary"
                  type="submit"
                  disabled={
                    !!working || (status === "password-required" && !password)
                  }
                >
                  Unlock PDF
                </button>
                <p className="unlock-permission">
                  Use PDFs you own or have permission to unlock.
                </p>
              </form>
            )
          )}
          {!status && reason && (
            <>
              <p className="unlock-error" role="alert">
                {unlockMessages[reason]}
              </p>
              {canRetry && (
                <button onClick={() => void inspect()}>Try again</button>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
});
