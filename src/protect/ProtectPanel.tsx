import {
  forwardRef,
  useEffect,
  useEffectEvent,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { protectJob, prepareProtect } from "./service";
import { verifyPasswords } from "./verify";
import {
  ProtectFailure,
  PROTECT_ERROR,
  validPassword,
  type ProtectCode,
} from "./model";
import { LeaveTaskDialog } from "../LeaveTaskDialog";
import { TaskNotice } from "../TaskNotice";
import { ToolIcon } from "../ToolIcon";
import { safeFilename } from "../photos/model";
import { LIMITS } from "../core/contracts";
import { track } from "../analytics";
import "./protect.css";
export { prepareProtect };
export type ProtectHandle = { guard: (action: () => void) => void };
export const ProtectPanel = forwardRef<
  ProtectHandle,
  {
    seed: File[];
    consume: (files: File[]) => void;
    pause: boolean;
    publish: (file: File, pages: number) => void;
    replace: () => void;
    onDirty: (value: boolean) => void;
    onBusy: (value: boolean) => void;
  }
>(function ProtectPanel(
  { seed, consume, pause, publish, replace, onDirty, onBusy },
  ref,
) {
  const [file] = useState(() => seed[0]!);
  const [pages, setPages] = useState(0),
    [password, setPassword] = useState(""),
    [confirmation, setConfirmation] = useState(""),
    [visible, setVisible] = useState(false),
    [working, setWorking] = useState<"inspect" | "protect" | null>(null),
    [message, setMessage] = useState(""),
    [stage, setStage] = useState(""),
    [pending, setPending] = useState<{ action: () => void } | null>(null);
  const controller = useRef<AbortController | null>(null),
    alive = useRef(true),
    first = useRef<HTMLInputElement>(null),
    second = useRef<HTMLInputElement>(null);
  const [reason, setReason] = useState<ProtectCode | null>(null);
  const clear = () => {
    setPassword("");
    setConfirmation("");
    setVisible(false);
    if (first.current) first.current.value = "";
    if (second.current) second.current.value = "";
  };
  useImperativeHandle(
    ref,
    () => ({
      guard(action) {
        if (!controller.current) setPending({ action });
      },
    }),
    [],
  );
  useEffect(
    () => () => {
      alive.current = false;
      controller.current?.abort();
      if (first.current) first.current.value = "";
      if (second.current) second.current.value = "";
      onDirty(false);
      onBusy(false);
    },
    [onBusy, onDirty],
  );
  async function inspect() {
    if (controller.current) return;
    const job = new AbortController();
    controller.current = job;
    setWorking("inspect");
    setMessage("");
    setReason(null);
    onBusy(true);
    onDirty(true);
    try {
      const result = await protectJob(file, null, job.signal);
      if (alive.current && !job.signal.aborted) setPages(result.pages);
    } catch (error) {
      if (alive.current) {
        const failure =
          error instanceof ProtectFailure
            ? error
            : new ProtectFailure("ENGINE");
        setReason(failure.code);
        setMessage(failure.message);
      }
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
  async function run() {
    if (controller.current || !pages || !validPassword(password, confirmation))
      return;
    const job = new AbortController();
    controller.current = job;
    const secret = { value: password },
      started = performance.now();
    clear();
    setMessage("");
    setWorking("protect");
    setStage("Encrypting your PDF…");
    onBusy(true);
    const timer = setTimeout(() => job.abort("timeout"), LIMITS.timeoutMs);
    track("process_start", "protect", {
      fileCount: 1,
      totalBytes: file.size,
      pages,
    });
    try {
      const output = await protectJob(file, secret.value, job.signal);
      if (!output.bytes) throw new ProtectFailure("VERIFY");
      if (alive.current) setStage("Checking password protection…");
      await verifyPasswords(
        output.bytes,
        secret.value,
        output.pages,
        job.signal,
      );
      if (!alive.current || job.signal.aborted) return;
      track("process_success", "protect", {
        fileCount: 1,
        totalBytes: file.size,
        pages: output.pages,
        durationMs: performance.now() - started,
      });
      publish(
        new File(
          [output.bytes],
          safeFilename(file.name.replace(/\.pdf$/i, "") + "-protected.pdf"),
          { type: "application/pdf" },
        ),
        output.pages,
      );
    } catch (error) {
      const failure =
        job.signal.reason === "timeout"
          ? new ProtectFailure("TIMEOUT")
          : error instanceof ProtectFailure
            ? error
            : new ProtectFailure("ENGINE");
      track(
        failure.code === "CANCELLED" ? "process_cancel" : "process_failure",
        "protect",
        {
          reason:
            failure.code === "CANCELLED"
              ? "cancelled"
              : failure.code === "TIMEOUT"
                ? "timeout"
                : failure.code === "RESOURCE"
                  ? "resource_limit"
                  : "validation",
        },
      );
      if (alive.current) setMessage(failure.message);
    } finally {
      secret.value = "";
      clearTimeout(timer);
      if (controller.current === job) controller.current = null;
      if (alive.current) {
        setWorking(null);
        onBusy(false);
      }
    }
  }
  const valid = validPassword(password, confirmation);
  return (
    <section className="protect-task" aria-label="Protect PDF">
      {pending && (
        <LeaveTaskDialog
          description="Your selected PDF and passwords will be cleared."
          keep={() => setPending(null)}
          leave={() => {
            const action = pending.action;
            clear();
            setPending(null);
            action();
          }}
        />
      )}
      <div className="protect-file">
        <ToolIcon tool="protect" />
        <div>
          <strong>{file.name}</strong>
          <span>
            {pages > 0 ? `${pages} ${pages === 1 ? "page" : "pages"} · ` : ""}
            {file.size < 1048576
              ? `${Math.max(1, Math.round(file.size / 1024))} KB`
              : `${(file.size / 1048576).toFixed(1)} MB`}
          </span>
        </div>
        <button
          className="secondary"
          disabled={!!working}
          onClick={() => setPending({ action: replace })}
        >
          Choose another file
        </button>
      </div>
      {pages > 0 && (
        <form
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            void run();
          }}
        >
          <h2>Set a password to open this PDF</h2>
          <label htmlFor="protect-password">Opening password</label>
          <input
            ref={first}
            id="protect-password"
            type={visible ? "text" : "password"}
            value={password}
            disabled={!!working}
            autoComplete="off"
            autoCapitalize="off"
            spellCheck={false}
            aria-describedby="protect-password-help"
            onChange={(event) => {
              setPassword(event.target.value);
              setMessage("");
            }}
          />
          <label htmlFor="protect-confirmation">Confirm password</label>
          <input
            ref={second}
            id="protect-confirmation"
            type={visible ? "text" : "password"}
            value={confirmation}
            disabled={!!working}
            autoComplete="off"
            autoCapitalize="off"
            spellCheck={false}
            aria-describedby="protect-password-help"
            onChange={(event) => {
              setConfirmation(event.target.value);
              setMessage("");
            }}
          />
          <button
            type="button"
            className="secondary protect-reveal"
            disabled={!!working}
            aria-pressed={visible}
            onClick={() => setVisible(!visible)}
          >
            {visible ? "Hide passwords" : "Show passwords"}
          </button>
          <p id="protect-password-help">
            Use a long, unique password with at least 8 characters. We cannot
            recover a forgotten password.
          </p>
          {password && !validPassword(password) && (
            <p role="status">{PROTECT_ERROR.PASSWORD}</p>
          )}
          {confirmation && password !== confirmation && (
            <p role="status">Passwords do not match.</p>
          )}
          <p className="protect-security">
            AES-256 opening protection. Anyone with the password can read, copy
            or print the content.
          </p>
          <button type="submit" disabled={!valid || !!working}>
            Protect PDF
          </button>
        </form>
      )}
      {message && (
        <p className="protect-error" role="alert">
          {message}
        </p>
      )}
      {!pages &&
        !working &&
        reason &&
        ["ENGINE", "TIMEOUT", "CANCELLED"].includes(reason) && (
          <button className="secondary" onClick={() => void inspect()}>
            Try again
          </button>
        )}
      {working && (
        <TaskNotice
          title={
            working === "inspect"
              ? "Checking your PDF…"
              : "Protecting your PDF…"
          }
          working
          message={
            working === "inspect"
              ? "Checking whether this PDF can be protected safely…"
              : stage
          }
          close={() => {
            clear();
            controller.current?.abort();
          }}
        />
      )}
    </section>
  );
});
