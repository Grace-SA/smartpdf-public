import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { writeFile, access } from "node:fs/promises";
import path from "node:path";
import { request } from "node:http";
import { createPdfExcelService } from "../server/pdf-to-excel/service.mjs";
let service: Awaited<ReturnType<typeof createPdfExcelService>>,
  url: string,
  cookie: string;
async function session() {
  const r = await fetch(url + "/session");
  return r.headers.get("set-cookie")!.split(";")[0]!;
}
async function upload(extra = "", headers: Record<string, string> = {}) {
  return fetch(url + "/jobs" + extra, {
    method: "POST",
    headers: { Cookie: cookie, "Content-Type": "application/pdf", ...headers },
    body: "%PDF-1.7\nsynthetic",
  });
}
async function result(id: string) {
  for (let i = 0; i < 60; i++) {
    const r = await fetch(url + "/jobs/" + id, { headers: { Cookie: cookie } });
    const j = await r.json();
    if (["succeeded", "failed"].includes(j.state)) return j;
    await new Promise((r) => setTimeout(r, 10));
  }
  throw Error("timeout");
}
describe("PDF to Excel task gateway", () => {
  beforeEach(async () => {
    service = await createPdfExcelService({
      run: async (job) => {
        await writeFile(
          path.join(job.dir, "output.xlsx"),
          Buffer.from("504b030473616d706c65", "hex"),
        );
        return { tables: 1, sheets: 1, warnings: [] };
      },
    });
    await new Promise<void>((r) => service.server.listen(0, "127.0.0.1", r));
    const a = service.server.address();
    url = `http://127.0.0.1:${typeof a === "object" && a ? a.port : 0}/api/pdf-to-excel`;
    cookie = await session();
  });
  afterEach(async () => {
    await service.close();
  });
  it("requires a session", async () =>
    expect((await fetch(url + "/jobs", { method: "POST" })).status).toBe(401));
  it("renews browser and server session lifetimes when reconnecting or starting a job", async () => {
    const reconnect = await fetch(url + "/session", {
      headers: { Cookie: cookie },
    });
    expect(reconnect.headers.get("set-cookie")).toContain(cookie);
    const started = await upload("?ocr=false");
    expect(started.headers.get("set-cookie")).toContain(cookie);
    expect(started.headers.get("set-cookie")).toContain("Max-Age=840");
  });
  it("rejects cross-origin mutation", async () =>
    expect(
      (await upload("", { Origin: "https://attacker.example" })).status,
    ).toBe(403));
  it("rejects forged content type", async () =>
    expect((await upload("", { "Content-Type": "text/plain" })).status).toBe(
      415,
    ));
  it("rejects invalid options", async () =>
    expect((await upload("?layout=evil")).status).toBe(400));
  it("reports unavailable OCR", async () =>
    expect((await upload("?ocr=true")).status).toBe(400));
  it("isolates jobs by session", async () => {
    const r = await upload("?ocr=false");
    const { id } = await r.json();
    const other = await session();
    expect(
      (await fetch(url + "/jobs/" + id, { headers: { Cookie: other } })).status,
    ).toBe(404);
  });
  it("converts, downloads, deletes and removes files", async () => {
    const r = await upload("?ocr=false");
    expect(r.status).toBe(202);
    const { id } = await r.json();
    expect((await result(id)).state).toBe("succeeded");
    expect(
      (
        await fetch(url + "/jobs/" + id + "/download", {
          headers: { Cookie: cookie },
        })
      ).status,
    ).toBe(200);
    expect(
      (
        await fetch(url + "/jobs/" + id, {
          method: "DELETE",
          headers: { Cookie: cookie },
        })
      ).status,
    ).toBe(200);
    expect(
      (await fetch(url + "/jobs/" + id, { headers: { Cookie: cookie } }))
        .status,
    ).toBe(404);
    await expect(access(path.join(service.root, id))).rejects.toThrow();
  });
  it("bounds per-session jobs", async () => {
    await upload("?ocr=false");
    await upload("?ocr=false");
    expect((await upload("?ocr=false")).status).toBe(429);
  });
  it("reserves capacity before concurrent uploads enter filesystem work", async () => {
    const responses = await Promise.all([
      upload("?ocr=false"),
      upload("?ocr=false"),
      upload("?ocr=false"),
    ]);
    expect(responses.filter((r) => r.status === 202)).toHaveLength(2);
    expect(responses.filter((r) => r.status === 429)).toHaveLength(1);
  });
  it("survives a malformed absolute request target", async () => {
    const origin = new URL(url);
    const status = await new Promise<number | undefined>((resolve, reject) => {
      const req = request(
        {
          hostname: origin.hostname,
          port: origin.port,
          path: "http://[",
          method: "GET",
        },
        (res) => {
          res.resume();
          res.on("end", () => resolve(res.statusCode));
        },
      );
      req.on("error", reject);
      req.end();
    });
    expect(status).toBe(500);
    expect((await fetch(url + "/session")).status).toBe(200);
  });
  it("rejects non-PDF bytes", async () => {
    const r = await fetch(url + "/jobs?ocr=false", {
      method: "POST",
      headers: { Cookie: cookie, "Content-Type": "application/pdf" },
      body: "not a pdf",
    });
    expect(r.status).toBe(400);
  });
  it("cancels a running conversion and cleans up", async () => {
    await service.close();
    let aborted = false;
    service = await createPdfExcelService({
      run: (_j, { signal }) =>
        new Promise((_resolve, reject) => {
          signal.addEventListener(
            "abort",
            () => {
              aborted = true;
              reject(Error("aborted"));
            },
            { once: true },
          );
        }),
    });
    await new Promise<void>((r) => service.server.listen(0, "127.0.0.1", r));
    const a = service.server.address();
    url = `http://127.0.0.1:${typeof a === "object" && a ? a.port : 0}/api/pdf-to-excel`;
    cookie = await session();
    const { id } = await (await upload("?ocr=false")).json();
    await fetch(url + "/jobs/" + id, {
      method: "DELETE",
      headers: { Cookie: cookie },
    });
    expect(aborted).toBe(true);
    await expect(access(path.join(service.root, id))).rejects.toThrow();
  });
});

it("expires temporary files even when a client never deletes a completed job", async () => {
  const expiring = await createPdfExcelService({
    ttlMs: 80,
    run: async (job) => {
      await writeFile(
        path.join(job.dir, "output.xlsx"),
        Buffer.from("504b030473616d706c65", "hex"),
      );
      return { tables: 1 };
    },
  });
  try {
    await new Promise<void>((r) => expiring.server.listen(0, "127.0.0.1", r));
    const a = expiring.server.address();
    const endpoint = `http://127.0.0.1:${typeof a === "object" && a ? a.port : 0}/api/pdf-to-excel`;
    const session = await fetch(endpoint + "/session");
    const ownCookie = session.headers.get("set-cookie")!.split(";")[0]!;
    const created = await fetch(endpoint + "/jobs?ocr=false", {
      method: "POST",
      headers: { Cookie: ownCookie, "Content-Type": "application/pdf" },
      body: "%PDF-test",
    });
    const { id } = await created.json();
    await new Promise((r) => setTimeout(r, 240));
    await expect(access(path.join(expiring.root, id))).rejects.toThrow();
  } finally {
    await expiring.close();
  }
});

it("does not report a non-workbook engine output as success", async () => {
  const invalid = await createPdfExcelService({
    run: async (job) => {
      await writeFile(
        path.join(job.dir, "output.xlsx"),
        "plain text, not XLSX",
      );
      return { tables: 1 };
    },
  });
  try {
    await new Promise<void>((r) => invalid.server.listen(0, "127.0.0.1", r));
    const a = invalid.server.address();
    const endpoint = `http://127.0.0.1:${typeof a === "object" && a ? a.port : 0}/api/pdf-to-excel`;
    const session = await fetch(endpoint + "/session");
    const ownCookie = session.headers.get("set-cookie")!.split(";")[0]!;
    const { id } = await (
      await fetch(endpoint + "/jobs?ocr=false", {
        method: "POST",
        headers: { Cookie: ownCookie, "Content-Type": "application/pdf" },
        body: "%PDF-test",
      })
    ).json();
    let state = "";
    for (let i = 0; i < 30; i++) {
      state = (
        await (
          await fetch(endpoint + "/jobs/" + id, {
            headers: { Cookie: ownCookie },
          })
        ).json()
      ).state;
      if (state === "failed") break;
      await new Promise((r) => setTimeout(r, 10));
    }
    expect(state).toBe("failed");
    expect(
      (
        await fetch(endpoint + "/jobs/" + id + "/download", {
          headers: { Cookie: ownCookie },
        })
      ).status,
    ).toBe(409);
  } finally {
    await invalid.close();
  }
});
