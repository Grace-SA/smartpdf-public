// Run inside the isolated Linux container with synthetic fixtures mounted read-only.
import assert from "node:assert/strict";
import { readFile, writeFile, mkdir, readdir, access } from "node:fs/promises";

const base = "http://127.0.0.1:4290/api/pdf-to-excel";
let response;
for (let i = 0; i < 40; i++) {
  try {
    response = await fetch(base + "/session");
    if (response.ok) break;
  } catch {}
  await new Promise((resolve) => setTimeout(resolve, 500));
}
assert.ok(response?.ok, "Service did not become ready");
const metadata = await response.json();
assert.equal(metadata.available, true);
assert.equal(metadata.ocr, true);
const cookieHeader = response.headers.get("set-cookie");
assert.match(cookieHeader, /Secure/);
const cookie = cookieHeader.split(";")[0];
await mkdir("/tmp/smoke-workbooks");
for (const name of ["ruled", "merged", "scan-chinese"]) {
  const upload = await fetch(base + "/jobs?ocr=true", {
    method: "POST",
    headers: { Cookie: cookie, "Content-Type": "application/pdf" },
    body: await readFile("/fixtures/" + name + ".pdf"),
  });
  assert.equal(upload.status, 202);
  const { id } = await upload.json();
  let result;
  for (let i = 0; i < 360; i++) {
    result = await (
      await fetch(base + "/jobs/" + id, { headers: { Cookie: cookie } })
    ).json();
    if (["succeeded", "failed"].includes(result.state)) break;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  assert.equal(result.state, "succeeded", result.error);
  const download = await fetch(base + "/jobs/" + id + "/download", {
    headers: { Cookie: cookie },
  });
  assert.equal(download.status, 200);
  await writeFile(
    "/tmp/smoke-workbooks/" + name + ".xlsx",
    Buffer.from(await download.arrayBuffer()),
  );
  const roots = (await readdir("/tmp")).filter((entry) =>
    entry.startsWith("smartpdf-excel-"),
  );
  assert.equal(roots.length, 1);
  const dir = "/tmp/" + roots[0] + "/" + id;
  await assert.rejects(access(dir + "/input.pdf"));
  assert.equal(
    (
      await fetch(base + "/jobs/" + id, {
        method: "DELETE",
        headers: { Cookie: cookie },
      })
    ).status,
    200,
  );
  await assert.rejects(access(dir));
  console.log("Container conversion and cleanup passed: " + name);
}
