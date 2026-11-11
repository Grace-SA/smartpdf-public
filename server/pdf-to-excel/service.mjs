import { createServer } from "node:http";
import { randomBytes } from "node:crypto";
import {
  mkdtemp,
  mkdir,
  rm,
  readFile,
  writeFile,
  stat,
} from "node:fs/promises";
import { createWriteStream, createReadStream } from "node:fs";
import { pipeline } from "node:stream/promises";
import { Transform } from "node:stream";
import { spawn } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
const MAX = 30 * 1024 * 1024;
const runner = fileURLToPath(new URL("./convert.py", import.meta.url));
const token = () => randomBytes(24).toString("hex");
const json = (res, status, value) => {
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
  });
  res.end(JSON.stringify(value));
};
export function runConversion(job, { python, signal, timeoutMs = 180000 }) {
  return new Promise((resolve, reject) => {
    const child = spawn(
      python,
      [
        runner,
        path.join(job.dir, "input.pdf"),
        path.join(job.dir, "output.xlsx"),
        JSON.stringify(job.options),
      ],
      {
        stdio: ["ignore", "pipe", "pipe"],
        env: { ...process.env, PYTHONUNBUFFERED: "1", OMP_NUM_THREADS: "2" },
      },
    );
    let out = "";
    let bytes = 0;
    let timedOut = false;
    const kill = () => child.kill("SIGKILL");
    const timer = setTimeout(() => {
      timedOut = true;
      kill();
    }, timeoutMs);
    signal.addEventListener("abort", kill, { once: true });
    if (signal.aborted) kill();
    child.stdout.on("data", (chunk) => {
      bytes += chunk.length;
      if (bytes > 2 * 1024 * 1024) kill();
      else out += chunk.toString();
    });
    // Parser/OCR diagnostics can contain document content. Never log them.
    child.stderr.resume();
    child.once("error", () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", kill);
      reject(Error("The conversion engine could not start."));
    });
    child.once("close", (code) => {
      clearTimeout(timer);
      signal.removeEventListener("abort", kill);
      if (signal.aborted) return reject(Error("Conversion cancelled."));
      if (timedOut)
        return reject(Error("Conversion timed out. Try fewer pages."));
      try {
        const value = JSON.parse(out.trim().split("\n").at(-1));
        if (code || value.error)
          reject(Error(value.error || "Conversion failed."));
        else resolve(value);
      } catch {
        reject(Error("The conversion engine returned an invalid result."));
      }
    });
  });
}
export async function createPdfExcelService(options = {}) {
  const python = options.python || process.env.PDF_EXCEL_PYTHON || "python3";
  const ttl = options.ttlMs || 14 * 60 * 1000;
  const root = await mkdtemp(
    path.join(options.tempRoot || tmpdir(), "smartpdf-excel-"),
  );
  const jobs = new Map();
  const sessions = new Map();
  const queue = [];
  let running = false;
  let closing = false;
  const run = options.run || runConversion;
  const metadata = {
    available: true,
    ocr: options.ocr ?? process.env.PDF_EXCEL_OCR === "true",
    region: process.env.PDF_EXCEL_REGION || "Self-hosted conversion server",
    retentionMinutes: Math.ceil((ttl + 10000) / 60000),
  };
  if (!options.run) {
    metadata.available = await new Promise((resolve) => {
      const c = spawn(python, [
        "-c",
        `import pdfplumber,openpyxl,pypdf,os,importlib.util
from pathlib import Path
models=os.environ.get('PDF_EXCEL_MODELS')
assert models or os.environ.get('NODE_ENV') != 'production', 'Layout models required in production'
if models:
 assert importlib.util.find_spec('docling'), 'Missing layout runtime'
 root=Path(models)
 assert (root/'docling-project--docling-layout-heron/model.safetensors').is_file()
 assert (root/'docling-project--docling-models/model_artifacts/tableformer/accurate/tableformer_accurate.safetensors').is_file()
`,
      ]);
      const t = setTimeout(() => c.kill("SIGKILL"), 10000);
      c.on("error", () => resolve(false));
      c.on("close", (n) => {
        clearTimeout(t);
        resolve(n === 0);
      });
    });
    if (metadata.ocr)
      metadata.ocr = await new Promise((resolve) => {
        const c = spawn(python, ["-c", "import rapidocr_onnxruntime,cv2"]);
        const t = setTimeout(() => c.kill("SIGKILL"), 10000);
        c.on("error", () => resolve(false));
        c.on("close", (n) => {
          clearTimeout(t);
          resolve(n === 0);
        });
      });
  }
  const discard = async (job) => {
    job.state = "cancelled";
    job.controller.abort();
    jobs.delete(job.id);
    if (job.done) await job.done;
    await rm(job.dir, { recursive: true, force: true });
  };
  async function pump() {
    if (running || closing) return;
    running = true;
    try {
      while (queue.length && !closing) {
        const job = queue.shift();
        if (!jobs.has(job.id) || job.controller.signal.aborted) continue;
        job.state = "converting";
        job.done = (async () => {
          try {
            const result = await run(job, {
              python,
              signal: job.controller.signal,
              timeoutMs: options.timeoutMs,
            });
            if (job.controller.signal.aborted) return;
            const file = path.join(job.dir, "output.xlsx");
            const size = (await stat(file)).size;
            if (size < 4 || size > MAX)
              throw Error("The workbook size is invalid.");
            const head = (await readFile(file)).subarray(0, 4);
            if (head.toString("hex") !== "504b0304")
              throw Error("The output is not an Excel workbook.");
            job.result = result;
            job.state = "succeeded";
            await rm(path.join(job.dir, "input.pdf"), { force: true });
          } catch (error) {
            if (!job.controller.signal.aborted) {
              job.state = "failed";
              job.error = error.message;
              await rm(job.dir, { recursive: true, force: true });
            }
          }
        })();
        await job.done;
      }
    } finally {
      running = false;
    }
  }
  const sweep = setInterval(
    () => {
      const now = Date.now();
      for (const j of jobs.values()) if (j.expires <= now) void discard(j);
      for (const [id, expiry] of sessions)
        if (expiry <= now) sessions.delete(id);
    },
    Math.min(10000, ttl),
  );
  sweep.unref();
  const renewSession = (session, res) => {
    sessions.set(session, Date.now() + ttl);
    res.setHeader(
      "Set-Cookie",
      `pdf_excel_session=${session}; HttpOnly; SameSite=Strict; Path=/api/pdf-to-excel; Max-Age=${Math.ceil(ttl / 1000)}${options.secureCookies || process.env.NODE_ENV === "production" ? "; Secure" : ""}`,
    );
  };
  const server = createServer(async (req, res) => {
    res.setHeader("Cache-Control", "no-store");
    try {
      const url = new URL(req.url, "http://localhost");
      if (!url.pathname.startsWith("/api/pdf-to-excel/"))
        return json(res, 404, { error: "Not found." });
      const origin = req.headers.origin;
      if (origin) {
        let allowed = false;
        try {
          allowed =
            new URL(origin).host === req.headers.host ||
            origin === options.origin ||
            origin === process.env.PDF_EXCEL_ORIGIN;
        } catch {}
        if (!allowed) return json(res, 403, { error: "Origin not allowed." });
      }
      if (req.headers["sec-fetch-site"] === "cross-site")
        return json(res, 403, { error: "Origin not allowed." });
      let session = (req.headers.cookie || "").match(
        /(?:^|;\s*)pdf_excel_session=([a-f0-9]{48})(?:;|$)/,
      )?.[1];
      if (
        req.method === "GET" &&
        url.pathname === "/api/pdf-to-excel/session"
      ) {
        if (
          !session ||
          !sessions.has(session) ||
          sessions.get(session) <= Date.now()
        ) {
          if (sessions.size >= 1000)
            return json(res, 503, {
              error: "The service is busy. Try again shortly.",
            });
          session = token();
        }
        renewSession(session, res);
        return json(res, 200, metadata);
      }
      if (
        !session ||
        !sessions.has(session) ||
        sessions.get(session) <= Date.now()
      )
        return json(res, 401, {
          error: "Your session expired. Reconnect and try again.",
        });
      if (req.method === "POST" && url.pathname === "/api/pdf-to-excel/jobs") {
        if (!metadata.available)
          return json(res, 503, {
            error: "Conversion is unavailable. Try again shortly.",
          });
        if (
          jobs.size >= 16 ||
          [...jobs.values()].filter((j) => j.session === session).length >= 2
        )
          return json(res, 429, {
            error: "Finish or delete your previous conversion first.",
          });
        const pages = url.searchParams.get("pages") || "all";
        const layout = url.searchParams.get("layout") || "tables";
        const ocr = url.searchParams.has("ocr")
          ? url.searchParams.get("ocr") !== "false"
          : metadata.ocr;
        if (
          pages.length > 1000 ||
          !/^(?:all|[\d\s,-]+)$/.test(pages) ||
          !["tables", "single"].includes(layout)
        )
          return json(res, 400, { error: "Invalid conversion options." });
        if (ocr && !metadata.ocr)
          return json(res, 400, {
            error:
              "OCR is unavailable. Turn off scanned-page recognition or try later.",
          });
        if (
          !/^application\/pdf(?:;|$)/i.test(req.headers["content-type"] || "")
        )
          return json(res, 415, { error: "Upload a PDF file." });
        const length = Number(req.headers["content-length"]);
        if (Number.isFinite(length) && length > MAX)
          return json(res, 413, { error: "Choose a PDF up to 30 MiB." });
        const id = token();
        const dir = path.join(root, id);
        const job = {
          id,
          dir,
          session,
          state: "uploading",
          options: { pages, layout, ocr },
          controller: new AbortController(),
          expires: Date.now() + ttl,
        };
        renewSession(session, res);
        jobs.set(id, job);
        let bytes = 0;
        let prefix = Buffer.alloc(0);
        const uploadTimer = setTimeout(() => req.destroy(), 120000);
        try {
          // Reserve admission before the first await so concurrent uploads
          // cannot all pass the per-session/global capacity check.
          await mkdir(dir, { mode: 0o700 });
          await pipeline(
            req,
            new Transform({
              transform(chunk, _encoding, cb) {
                bytes += chunk.length;
                if (prefix.length < 5)
                  prefix = Buffer.concat([prefix, chunk]).subarray(0, 5);
                cb(
                  bytes > MAX ? Error("Choose a PDF up to 30 MiB.") : null,
                  chunk,
                );
              },
            }),
            createWriteStream(path.join(dir, "input.pdf"), {
              flags: "wx",
              mode: 0o600,
            }),
          );
          if (!bytes || prefix.toString() !== "%PDF-")
            throw Error("This file is not a PDF.");
          if (job.controller.signal.aborted) throw Error("Upload expired.");
          job.state = "queued";
          queue.push(job);
          json(res, 202, { id, state: "queued" });
          void pump();
        } catch (error) {
          await discard(job);
          if (!res.destroyed) json(res, 400, { error: error.message });
        } finally {
          clearTimeout(uploadTimer);
        }
        return;
      }
      const match = url.pathname.match(
        /^\/api\/pdf-to-excel\/jobs\/([a-f0-9]{48})(\/download)?$/,
      );
      const job = match && jobs.get(match[1]);
      if (!job || job.session !== session || job.expires <= Date.now())
        return json(res, 404, {
          error: "This conversion expired or was deleted. Start again.",
        });
      if (req.method === "DELETE" && !match[2]) {
        await discard(job);
        return json(res, 200, { deleted: true });
      }
      if (req.method === "GET" && match[2]) {
        if (job.state !== "succeeded")
          return json(res, 409, { error: "The workbook is not ready." });
        res.writeHead(200, {
          "Content-Type":
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          "Content-Disposition": 'attachment; filename="converted.xlsx"',
          "X-Content-Type-Options": "nosniff",
        });
        await pipeline(
          createReadStream(path.join(job.dir, "output.xlsx")),
          res,
        );
        return;
      }
      if (req.method === "GET")
        return json(res, 200, {
          id: job.id,
          state: job.state,
          error: job.error,
          ...job.result,
        });
      json(res, 405, { error: "Method not allowed." });
    } catch {
      if (!res.headersSent)
        json(res, 500, {
          error: "The conversion service could not complete this request.",
        });
      else res.destroy();
    }
  });
  server.requestTimeout = 125000;
  server.headersTimeout = 15000;
  return {
    server,
    root,
    async close() {
      closing = true;
      clearInterval(sweep);
      await Promise.all([...jobs.values()].map(discard));
      await new Promise((resolve) => server.close(resolve));
      await rm(root, { recursive: true, force: true });
    },
  };
}
if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  const service = await createPdfExcelService();
  service.server.listen(
    Number(process.env.PDF_EXCEL_PORT || 4290),
    process.env.PDF_EXCEL_HOST || "127.0.0.1",
    () =>
      console.log(
        "PDF to Excel service: http://127.0.0.1:" +
          (process.env.PDF_EXCEL_PORT || 4290),
      ),
  );
  for (const sig of ["SIGINT", "SIGTERM"])
    process.once(sig, () => void service.close().then(() => process.exit(0)));
}
