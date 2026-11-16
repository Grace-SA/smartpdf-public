import { createServer } from "node:http";
import {
  randomBytes,
  randomUUID,
  createHmac,
  timingSafeEqual,
} from "node:crypto";
import { mkdir, writeFile, rm, readdir, stat } from "node:fs/promises";
import { createReadStream, createWriteStream, realpathSync } from "node:fs";
import { createStandby } from "./standby.mjs";
import { pipeline } from "node:stream/promises";
import { Transform } from "node:stream";
import { spawn } from "node:child_process";
import { Worker } from "node:worker_threads";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import { tmpdir } from "node:os";
import { performance } from "node:perf_hooks";

const UPLOAD_TIMEOUT_MS = 120000;
const terminal = new Set(["succeeded", "failed", "cancelled", "expired"]);
// Leave a minute for the 30-second cleanup sweep inside the one-hour promise.
const ttl = 59 * 60 * 1000;
const runner = fileURLToPath(new URL("./runner.py", import.meta.url));
async function outputOptions(req) {
  const chunks = [];
  let size = 0;
  const timeout = setTimeout(() => req.destroy(), 5000);
  try {
    for await (const chunk of req) {
      size += chunk.length;
      if (size > 2048) throw Error("options");
      chunks.push(chunk);
    }
    const value = size
      ? JSON.parse(Buffer.concat(chunks).toString("utf8"))
      : {};
    const view =
      value?.revisionView === undefined ? "unchanged" : value.revisionView;
    const omit = value?.omitComments === undefined ? false : value.omitComments;
    if (
      !value ||
      Array.isArray(value) ||
      typeof value !== "object" ||
      Object.keys(value).some(
        (k) =>
          !["revisionView", "omitComments", "useAvailableFonts"].includes(k),
      ) ||
      !["unchanged", "final", "original"].includes(view) ||
      typeof omit !== "boolean" ||
      (value.useAvailableFonts !== undefined &&
        typeof value.useAvailableFonts !== "boolean")
    )
      throw Error("options");
    return {
      revisionView: view,
      omitComments: omit,
      ...(value.useAvailableFonts !== undefined
        ? { useAvailableFonts: value.useAvailableFonts }
        : {}),
    };
  } finally {
    clearTimeout(timeout);
  }
}

export function checkPdf(file, policyOrKind = "word") {
  const policy = typeof policyOrKind === "object" ? policyOrKind : undefined;
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL("./pdf-check.mjs", import.meta.url), {
      workerData: {
        file,
        policy,
        maxPages: policyOrKind === "excel" ? 500 : 200,
      },
      resourceLimits: { maxOldGenerationSizeMb: 192 },
    });
    const finish = (error, value) => {
      clearTimeout(timer);
      void worker.terminate();
      if (error) reject(error);
      else resolve(value);
    };
    const timer = setTimeout(
      () => finish(new Error("PDF validation timed out")),
      10000,
    );
    worker.once("message", (value) =>
      finish(value.error ? new Error("Invalid PDF output") : null, value),
    );
    worker.once("error", (error) => finish(error));
    worker.once("exit", (code) => {
      if (code) finish(new Error("PDF validation failed"));
    });
  });
}

function linuxPath(value) {
  return value
    .replace(/^([A-Za-z]):[\\/]/, (_, drive) => `/mnt/${drive.toLowerCase()}/`)
    .replaceAll("\\", "/");
}

export function runStirling(job, update, adapter = runner, timeoutMs = 300000) {
  return new Promise((resolve, reject) => {
    if (!Number.isInteger(timeoutMs) || timeoutMs < 1000 || timeoutMs > 3600000)
      throw new Error("Invalid conversion worker deadline");
    const windows = process.platform === "win32";
    const command = windows
      ? process.env.WORD_WSL || "C:/Program Files/WSL/wsl.exe"
      : "python3";
    const control = job.warmToken || job.discardToken;
    const script = control
      ? fileURLToPath(new URL("./warm.py", import.meta.url))
      : adapter;
    const mapped = (value) =>
      windows && !value.startsWith("--")
        ? linuxPath(realpathSync(value))
        : value;
    const values = job.discardToken
      ? ["--discard", job.directory, job.discardToken]
      : [
          mapped(job.directory),
          ...(!control && job.kind === "excel" ? ["excel"] : []),
          ...(job.warmToken
            ? [job.warmToken]
            : [
                ...(job.standby
                  ? ["--standby", job.standby.name, job.standby.token]
                  : []),
                ...(job.budgetSeconds
                  ? ["--budget", String(job.budgetSeconds)]
                  : []),
              ]),
        ];
    const args = windows
      ? [
          "-d",
          "Ubuntu-24.04",
          "-u",
          "root",
          "--",
          "python3",
          linuxPath(realpathSync(script)),
          ...values,
        ]
      : [script, ...values];
    const child = spawn(command, args, {
      windowsHide: true,
      stdio: ["ignore", "pipe", "ignore"],
    });
    const deadline = setTimeout(() => {
      child.kill();
      reject(
        Object.assign(new Error("Conversion worker timed out."), {
          unsafe: true,
          code: "WORKER_TIMEOUT",
        }),
      );
    }, timeoutMs);
    let buffer = "";
    let error;
    let cleanupFailed = false;
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (text) => {
      buffer += text;
      if (buffer.length > 32000) {
        cleanupFailed = true;
        child.kill();
        return;
      }
      let index;
      while ((index = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, index);
        buffer = buffer.slice(index + 1);
        try {
          const value = JSON.parse(line);
          if (value.error) error = { message: value.error, code: value.code };
          if (value.cleanupFailed) cleanupFailed = true;
          update(value);
        } catch {
          cleanupFailed = true;
          child.kill();
        }
      }
    });
    child.once("error", (error) => {
      clearTimeout(deadline);
      reject(error);
    });
    child.once("close", (code) => {
      clearTimeout(deadline);
      if (cleanupFailed)
        reject(
          Object.assign(
            new Error("Conversion cleanup requires operator attention."),
            { unsafe: true, code: "CLEANUP_FAILED" },
          ),
        );
      else if (error || code)
        reject(
          Object.assign(
            new Error(
              error?.message ||
                "Conversion service is unavailable. Try again later.",
            ),
            { code: error?.code },
          ),
        );
      else resolve();
    });
  });
}

export async function createWordService(options = {}) {
  const ppt = options.format === "ppt";
  const pdfword = options.format === "pdfword";
  const processingTtlMs = pdfword
    ? (options.processingTtlMs ?? 16 * 60000)
    : 16 * 60000;
  if (
    !Number.isInteger(processingTtlMs) ||
    processingTtlMs < 16 * 60000 ||
    processingTtlMs > 3600000
  )
    throw new Error("Invalid processing expiry");
  const outputName = pdfword ? "output.docx" : "output.pdf";
  const outputMime = pdfword
    ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    : "application/pdf";
  const maxInputBytes = (ppt ? 60 : 30) * 1024 ** 2;
  const api = pdfword ? "/api/pdfword" : ppt ? "/api/ppt" : "/api/word";
  const inputFor = (kind) =>
    pdfword
      ? "input.pdf"
      : ppt
        ? "input.pptx"
        : kind === "excel"
          ? "input.xlsx"
          : "input.docx";
  const inputMime = pdfword
    ? "application/pdf"
    : ppt
      ? "application/vnd.openxmlformats-officedocument.presentationml.presentation"
      : "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  if (ppt && !options.execute)
    throw new Error("PPT requires its dedicated executor");
  if (pdfword && (!options.execute || !options.validate))
    throw new Error(
      "PDF to Word requires its dedicated executor and validator",
    );
  const root = path.resolve(
    options.root ||
      process.env.WORD_DATA_DIR ||
      path.join(tmpdir(), ppt ? "smartpdf-ppt-tasks" : "smartpdf-word-tasks"),
  );
  const origin =
    options.origin || process.env.WORD_PUBLIC_ORIGIN || "http://127.0.0.1:4240";
  const secure = origin.startsWith("https://");
  if (!secure && !/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(origin))
    throw new Error("HTTPS required");
  if (new URL(origin).origin !== origin)
    throw new Error("Configure an exact public origin without a path.");
  await mkdir(root, { recursive: true, mode: 0o700 });
  // Dedicated storage contains only disposable anonymous tasks. A restart invalidates cookies.
  for (const entry of await readdir(root)) {
    if (/^[a-f0-9-]{36}$/.test(entry))
      await rm(path.join(root, entry), { recursive: true, force: true });
  }
  const secret = randomBytes(32);
  const jobs = new Map();
  const rates = new Map();
  let active = false;
  let stopped = false;
  let unhealthy = false;
  function markUnhealthy() {
    unhealthy = true;
    options.onUnsafe?.();
  }
  const pool =
    !options.execute && process.env.WORD_PREWARM !== "false"
      ? createStandby({
          root,
          run: runStirling,
          broken: () => {
            markUnhealthy();
          },
        })
      : undefined;
  const execute =
    options.execute ||
    (async (job, update) => {
      const started = performance.now();
      update({ state: "starting" });
      job.standby = await pool?.take(job);
      if (terminal.has(job.state)) {
        await pool?.release(job.standby);
        return;
      }
      job.budgetSeconds = Math.max(
        1,
        240 - (performance.now() - started) / 1000,
      );
      await runStirling(job, update);
      const next = [...jobs.values()].find((value) => value.state === "queued");
      if (
        !stopped &&
        !unhealthy &&
        (!next || next.options?.revisionView === "unchanged")
      )
        pool?.ensure();
    });
  const validate = options.validate || checkPdf;
  const now = options.now || Date.now;
  const signature = (value) =>
    createHmac("sha256", secret).update(value).digest("hex");
  function session(req, res, create = false, kind = "word") {
    const cookie = (req.headers.cookie || "")
      .split(";")
      .map((s) => s.trim())
      .find((s) => s.startsWith(`${kind}_session=`))
      ?.slice(`${kind}_session=`.length);
    if (cookie && /^[a-f0-9]{64}\.[a-f0-9]{64}$/.test(cookie)) {
      const [id, sig] = cookie.split(".");
      if (timingSafeEqual(Buffer.from(sig), Buffer.from(signature(id))))
        return id;
    }
    if (!create) return null;
    const id = randomBytes(32).toString("hex");
    res.setHeader(
      "Set-Cookie",
      `${kind}_session=${id}.${signature(id)}; Path=/api/${kind}; HttpOnly; SameSite=Strict; Max-Age=3600${secure ? "; Secure" : ""}`,
    );
    return id;
  }
  const view = (job) => ({
    id: job.id,
    state: job.state,
    pages: job.pages,
    warnings: job.warnings,
    progress: job.progress,
    error: job.error,
    failureCode: job.failureCode,
    expiresAt: job.expiresAt,
    queueAhead:
      job.state === "queued" && !options.admit
        ? Math.max(
            0,
            [...jobs.values()]
              .filter((value) => value.state === "queued")
              .findIndex((value) => value.id === job.id) + (active ? 1 : 0),
          )
        : undefined,
    cleanupPending:
      (job.state === "cancelled" || job.state === "expired") &&
      !!(job.running || job.uploading || job.cancelWrite || job.erasing),
    options: job.options,
  });
  async function erase(job) {
    if (job.running || job.uploading) return;
    await job.cancelWrite;
    if (job.erasing) return job.erasing;
    const pending = rm(job.directory, { recursive: true, force: true });
    job.erasing = pending;
    try {
      await pending;
    } finally {
      if (job.erasing === pending) delete job.erasing;
    }
  }
  async function drain() {
    if (active || unhealthy || stopped) return;
    const job = [...jobs.values()].find((j) => j.state === "queued");
    if (!job) {
      if (!stopped && !unhealthy) pool?.ensure();
      return;
    }
    active = true;
    job.running = true;
    const admission = new AbortController();
    job.admission = admission;
    let release;
    try {
      release = await options.admit?.(job, admission.signal);
      if (terminal.has(job.state)) return;
      await execute(job, (value) => {
        if (terminal.has(job.state)) return;
        if (
          [
            "checking",
            "starting",
            "preparing",
            "converting",
            "checking-result",
          ].includes(value.state)
        )
          job.state = value.state;
        if (Array.isArray(value.warnings)) job.warnings = value.warnings;
        if (
          pdfword &&
          Number.isInteger(value.completedPages) &&
          Number.isInteger(value.totalPages) &&
          value.completedPages >= 0 &&
          value.completedPages <= value.totalPages &&
          value.totalPages <= 200
        )
          job.progress = {
            completedPages: value.completedPages,
            totalPages: value.totalPages,
          };
      });
      if (!terminal.has(job.state)) {
        job.state = "checking-result";
        let result;
        try {
          result = await validate(
            path.join(job.directory, outputName),
            job.kind,
          );
        } catch {
          throw Object.assign(new Error("Invalid conversion output"), {
            code: "OUTPUT_INVALID",
          });
        }
        // Do not announce success while the uploaded source still exists.
        await rm(path.join(job.directory, inputFor(job.kind)), { force: true });
        await rm(path.join(job.directory, "prepared.xlsx"), { force: true });
        await rm(path.join(job.directory, "prepared.docx"), { force: true });
        await rm(path.join(job.directory, "sanitized.docx"), { force: true });
        await rm(path.join(job.directory, "options.json"), { force: true });
        if (ppt || pdfword)
          await rm(path.join(job.directory, "expected.json"), { force: true });
        if (!terminal.has(job.state)) {
          job.pages = result.pages;
          job.state = "succeeded";
          job.expiresAt = now() + ttl;
        }
      }
    } catch (error) {
      if (error.unsafe) markUnhealthy();
      if (!terminal.has(job.state)) {
        job.state = "failed";
        job.expiresAt = now() + 60000;
        job.failureCode = error.code;
        job.error =
          error.code === "INPUT_REJECTED"
            ? error.message
            : pdfword
              ? "Conversion could not finish. Retry, or choose another PDF."
              : `Conversion could not finish. Try again, or export from ${ppt ? "PowerPoint" : job.kind === "excel" ? "Excel" : "Word"}.`;
      }
    } finally {
      job.running = false;
      active = false;
      try {
        await job.cancelWrite;
        await rm(path.join(job.directory, inputFor(job.kind)), { force: true });
        await rm(path.join(job.directory, "prepared.xlsx"), { force: true });
        if (job.state !== "succeeded") await erase(job);
      } catch {
        markUnhealthy();
        job.state = "failed";
        job.error = "Temporary-file cleanup requires operator attention.";
        job.failureCode = "CLEANUP_FAILED";
      }
      delete job.admission;
      try {
        await release?.(!unhealthy);
      } catch {
        markUnhealthy();
      }
      void drain();
    }
  }
  async function cancel(job, state = "cancelled") {
    job.state = state;
    if (state === "cancelled")
      job.expiresAt = Math.min(job.expiresAt, now() + 60000);
    job.error = undefined;
    if (job.running) {
      job.cancelWrite ??= writeFile(
        path.join(job.directory, "cancel"),
        "cancel",
      );
      await job.cancelWrite;
      delete job.cancelWrite;
    }
    job.admission?.abort();
    await pool?.cancel(job);
    job.uploadController?.abort();
    await erase(job);
  }
  async function sweep() {
    for (const [id, job] of jobs) {
      if (now() >= job.expiresAt) {
        await cancel(job, "expired");
        if (!job.running && !job.uploading) jobs.delete(id);
      }
    }
    for (const [key, value] of rates)
      if (now() - value.time > 60000) rates.delete(key);
  }
  const timer = setInterval(
    () =>
      void sweep().catch(() => {
        markUnhealthy();
      }),
    30000,
  );
  timer.unref();
  function json(res, code, value) {
    res.writeHead(code, {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    });
    res.end(JSON.stringify(value));
  }
  const server = createServer(async (req, res) => {
    try {
      const url = new URL(req.url, origin);
      if (ppt || pdfword) {
        if (!url.pathname.startsWith(api + "/"))
          return json(res, 404, { error: "Unknown conversion endpoint." });
        url.pathname = "/api/word/" + url.pathname.slice(api.length + 1);
      }
      const kind = pdfword
        ? "pdfword"
        : ppt
          ? "ppt"
          : url.pathname.startsWith("/api/excel/")
            ? "excel"
            : "word";
      if (
        kind === "excel" &&
        !(options.enableExcel ?? process.env.ENABLE_EXCEL === "true")
      )
        return json(res, 404, {
          error: "This tool is not enabled on this server.",
        });
      if (kind === "excel")
        url.pathname = url.pathname.replace("/api/excel/", "/api/word/");
      const format = pdfword
        ? "PDF"
        : ppt
          ? "PPTX"
          : kind === "excel"
            ? "XLSX"
            : "DOCX";
      if (url.pathname === "/api/word/health" && req.method === "GET")
        return json(
          res,
          unhealthy || stopped || options.available?.() === false ? 503 : 200,
          {
            available:
              !unhealthy && !stopped && options.available?.() !== false,
          },
        );
      const mutation = !["GET", "HEAD"].includes(req.method);
      if (
        (mutation && req.headers.origin !== origin) ||
        (req.headers.origin && req.headers.origin !== origin)
      )
        return json(res, 403, {
          error: "Open this tool from its own website.",
        });
      const owner = session(
        req,
        res,
        url.pathname === "/api/word/session" && req.method === "GET",
        kind,
      );
      const key = owner || req.socket.remoteAddress;
      const rate = rates.get(key) || { time: now(), count: 0 };
      if (now() - rate.time > 60000) {
        rate.time = now();
        rate.count = 0;
      }
      if (rates.size >= 1024 && !rates.has(key))
        return json(res, 429, { error: "Service is busy. Try again shortly." });
      rates.set(key, rate);
      if (++rate.count > 180)
        return json(res, 429, {
          error: "Too many requests. Try again shortly.",
        });
      if (url.pathname === "/api/word/session" && req.method === "GET")
        return json(res, 200, {
          region:
            options.region ||
            process.env.WORD_PROCESSING_LABEL ||
            "This self-hosted conversion server",
          maxBytes: maxInputBytes,
          retentionMinutes: 60,
          mode:
            !secure && process.env.WORD_PROCESSING_MODE === "local"
              ? "local"
              : "cloud",
          ready: pool?.ready() ?? true,
          available: !unhealthy && !stopped && options.available?.() !== false,
          capabilities: pdfword
            ? options.capabilities || {}
            : ppt
              ? {}
              : {
                  revisionViews: ["final", "original"],
                  omitComments: true,
                  availableFonts: true,
                },
        });
      if (!owner)
        return json(res, 401, {
          error: "Reopen this tool to start a new session.",
        });
      if (url.pathname === "/api/word/jobs" && req.method === "POST") {
        let settings;
        try {
          settings = await outputOptions(req);
          if (
            (ppt || pdfword) &&
            (settings.revisionView !== "unchanged" ||
              settings.omitComments ||
              settings.useAvailableFonts !== undefined)
          )
            throw new Error("PPT does not accept Word options");
        } catch {
          return json(res, 400, {
            error: "Choose valid document output options.",
          });
        }
        await sweep();
        if (unhealthy || stopped || options.available?.() === false)
          return json(res, 503, {
            error: "Conversion is temporarily unavailable.",
          });
        if (
          [...jobs.values()].filter((j) => !terminal.has(j.state)).length >=
            3 ||
          [...jobs.values()].filter(
            (j) => j.owner === owner && !terminal.has(j.state),
          ).length >= 1 ||
          jobs.size >= 24
        )
          return json(res, 429, {
            error: "The conversion queue is full. Try again shortly.",
          });
        const id = randomUUID();
        const job = {
          id,
          kind,
          owner,
          directory: path.join(root, id),
          state: "created",
          warnings: [],
          options: settings,
          expiresAt: now() + 60000,
        };
        await mkdir(job.directory, { mode: 0o700 });
        if (kind === "word")
          await writeFile(
            path.join(job.directory, "options.json"),
            JSON.stringify(settings),
            { mode: 0o600, flag: "wx" },
          );
        jobs.set(id, job);
        return json(res, 201, view(job));
      }
      const match = url.pathname.match(
        /^\/api\/word\/jobs\/([a-f0-9-]{36})(?:\/(input|result))?$/,
      );
      const job = match && jobs.get(match[1]);
      if (!job || job.owner !== owner || (job.kind || "word") !== kind)
        return json(res, 404, {
          error: "This conversion is unavailable or expired.",
        });
      if (now() >= job.expiresAt) {
        await cancel(job, "expired");
        return json(res, 410, {
          error: "This conversion has expired. Choose the document again.",
        });
      }
      if (req.method === "DELETE" && !match[2]) {
        await cancel(job);
        return json(res, 200, view(job));
      }
      if (req.method === "GET" && !match[2]) return json(res, 200, view(job));
      if (req.method === "PUT" && match[2] === "input") {
        if (job.state !== "created")
          return json(res, 409, { error: "This upload has already started." });
        if (
          req.headers["content-type"] !==
          (ppt || pdfword
            ? inputMime
            : kind === "excel"
              ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              : "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        )
          return json(res, 415, { error: `Choose an ${format} document.` });
        if (Number(req.headers["content-length"]) > maxInputBytes)
          return json(res, 413, {
            error: `Choose an ${format} up to ${ppt ? 60 : 30} MiB.`,
          });
        if (kind === "excel") {
          let settings;
          try {
            const header = req.headers["x-excel-options"];
            if (typeof header !== "string" || header.length > 4096)
              throw new Error("settings");
            settings = JSON.parse(header);
            if (
              !settings ||
              !Array.isArray(settings.sheets) ||
              settings.sheets.length < 1 ||
              settings.sheets.length > 50 ||
              settings.sheets.some(
                (i) => !Number.isInteger(i) || i < 0 || i >= 50,
              ) ||
              new Set(settings.sheets).size !== settings.sheets.length ||
              Object.keys(settings).some(
                (k) => !["sheets", "orientation", "paper", "scale"].includes(k),
              ) ||
              !["keep", "portrait", "landscape"].includes(
                settings.orientation,
              ) ||
              !["keep", "A4", "Letter"].includes(settings.paper) ||
              !["keep", "auto", "width", "page"].includes(settings.scale)
            )
              throw new Error("settings");
          } catch {
            return json(res, 400, {
              error: "Select visible worksheets and valid page settings.",
            });
          }
          await writeFile(
            path.join(job.directory, "options.json"),
            JSON.stringify(settings),
            { flag: "wx", mode: 0o600 },
          );
        }
        job.state = "uploading";
        job.uploading = true;
        job.expiresAt = now() + UPLOAD_TIMEOUT_MS + 10000;
        const controller = new AbortController();
        job.uploadController = controller;
        const timeout = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS);
        let bytes = 0;
        const limit = new Transform({
          transform(chunk, encoding, callback) {
            bytes += chunk.length;
            callback(bytes > maxInputBytes ? new Error("size") : null, chunk);
          },
        });
        let uploadStatus = 202;
        try {
          await pipeline(
            req,
            limit,
            createWriteStream(path.join(job.directory, inputFor(kind)), {
              flags: "wx",
              mode: 0o600,
            }),
            { signal: controller.signal },
          );
          if (!bytes) throw new Error("empty");
          if (job.state === "uploading") {
            job.state = "queued";
            // Include all three admitted slots, worker guards and cleanup margin.
            job.expiresAt = now() + processingTtlMs;
            void drain();
          }
        } catch {
          uploadStatus = 400;
          if (job.state === "uploading") {
            job.state = "failed";
            job.expiresAt = now() + 60000;
            job.error = `Upload did not finish. Choose a valid ${format} up to ${ppt ? 60 : 30} MiB and retry.`;
          }
        } finally {
          clearTimeout(timeout);
          job.uploading = false;
          job.uploadController = undefined;
          if (job.state === "failed" || job.state === "cancelled")
            await erase(job);
        }
        if (!res.destroyed) json(res, uploadStatus, view(job));
        return;
      }
      if (req.method === "GET" && match[2] === "result") {
        if (job.state !== "succeeded")
          return json(res, 409, {
            error: "The result is not ready or has been deleted.",
          });
        const file = path.join(job.directory, outputName);
        const size = (await stat(file)).size;
        res.writeHead(200, {
          "Content-Type": outputMime,
          "Content-Length": size,
          "Content-Disposition": `attachment; filename="converted.${pdfword ? "docx" : "pdf"}"`,
          "Cache-Control": "no-store",
          "X-Content-Type-Options": "nosniff",
        });
        await pipeline(createReadStream(file), res);
        return;
      }
      json(res, 405, { error: "Unsupported request." });
    } catch {
      if (!res.headersSent)
        json(res, 500, {
          error: "The conversion service is unavailable. Try again shortly.",
        });
      else res.destroy();
    }
  });
  server.requestTimeout = UPLOAD_TIMEOUT_MS + 10000;
  server.headersTimeout = 10000;
  pool?.ensure();
  return {
    server,
    jobs,
    sweep,
    pauseStandby: () => pool?.pause(),
    resumeStandby: () => pool?.resume(),
    async close() {
      stopped = true;
      clearInterval(timer);
      await Promise.all(
        [...jobs.values()]
          .filter((j) => !terminal.has(j.state))
          .map((j) => cancel(j)),
      );
      await pool?.close();
      await new Promise((resolve) => server.close(resolve));
    },
  };
}

if (
  process.argv[1] &&
  pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url
) {
  await runStirling({ directory: "--reap" }, () => {});
  const service = await createWordService();
  service.server.listen(
    Number(process.env.WORD_PORT || 4268),
    "127.0.0.1",
    () => console.log("Word conversion service ready on loopback."),
  );
  for (const signal of ["SIGINT", "SIGTERM"])
    process.once(signal, () => void service.close());
}
