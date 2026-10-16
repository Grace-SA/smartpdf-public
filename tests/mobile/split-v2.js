/* Synthetic local-only M4 acceptance. No PDF bytes or filenames are reported. */
const $ = (id) => document.getElementById(id),
  frame = $("app"),
  files = {};
const doc = () => frame.contentDocument,
  sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const button = (name) =>
  [...doc().querySelectorAll("button")].find(
    (b) => (b.getAttribute("aria-label") || b.textContent.trim()) === name,
  );
let report;
async function until(fn) {
  const end = performance.now() + 120000;
  while (!fn()) {
    if (performance.now() > end)
      throw Error(`等待超时：${report?.lastStep ?? "准备资源"}`);
    await sleep(30);
  }
}
async function click(name) {
  if (report) report.lastStep = `button: ${name}`;
  await until(() => button(name) && !button(name).disabled);
  button(name).click();
  await sleep(30);
}
function fill(selector, value) {
  const e = doc().querySelector(selector),
    w = frame.contentWindow;
  Object.getOwnPropertyDescriptor(
    e.tagName === "TEXTAREA"
      ? w.HTMLTextAreaElement.prototype
      : w.HTMLSelectElement.prototype,
    "value",
  ).set.call(e, value);
  e.dispatchEvent(
    new w.Event(e.tagName === "TEXTAREA" ? "input" : "change", {
      bubbles: true,
    }),
  );
}
const count = () => doc().querySelectorAll(".split-results li").length;
const pageCount = (n) => doc().body.textContent.includes(`Page 1 of ${n}`);
function check(name, pass) {
  report.checks.push({ name, pass });
  if (!pass) throw Error(name);
}
async function open(name, n) {
  const w = frame.contentWindow;
  function choose() {
    const t = new w.DataTransfer();
    t.items.add(
      new w.File([files[name]], "synthetic.pdf", { type: "application/pdf" }),
    );
    const input = doc().querySelector("#pdf-file");
    input.files = t.files;
    input.dispatchEvent(new w.Event("change", { bubbles: true }));
  }
  choose();
  if (name === "credentials") {
    await click("Stay here");
    check(
      "credential cancellation retains empty session",
      !doc().querySelector(".canvas-host canvas"),
    );
    choose();
    await click("Create copy without credentials");
  }
  if (report) report.lastStep = `preview: ${name}`;
  await until(() => pageCount(n));
}
async function clear() {
  await click("Clear session");
  await sleep(50);
  if (button("End session")) await click("End session");
  await until(() => !doc().querySelector(".canvas-host canvas"));
}
async function manual() {
  await open("ten", 10);
  await click("Split a PDF");
  fill(".split-task textarea", "1-3\n4-7\n8-10");
  $("manual").hidden = false;
  $("status").textContent =
    "准备好手动检查。下方十页样本已填好分组，按中文步骤完成后回传。";
}
(async () => {
  try {
    for (const name of ["ten", "hundred"]) {
      const r = await fetch(`/__m3/${name}.pdf`);
      if (!r.ok) throw Error("样本未就绪");
      files[name] = await r.arrayBuffer();
    }
    for (const name of ["credentials", "ordinary"]) {
      const r = await fetch(`/__m4/${name}.pdf`);
      if (!r.ok) throw Error("确认流程样本未就绪");
      files[name] = await r.arrayBuffer();
    }
    await until(() =>
      doc()?.body.textContent.includes("Ready for local processing"),
    );
    $("status").textContent = "准备完成。可以断网并开始离线测试。";
    $("run").disabled = false;
    $("manual-only").disabled = false;
  } catch (e) {
    $("status").textContent = `准备失败：${e.message}`;
  }
})();
function start(manualOnly) {
  report = {
    kind: "smartworks-split-device-check",
    harnessVersion: "m4-2",
    build: window.m0Build,
    userAgent: navigator.userAgent,
    checks: [],
    manualOnly,
    offlineUserConfirmed: !manualOnly && $("offline").checked,
  };
  $("run").disabled = $("manual-only").disabled = true;
}
$("manual-only").onclick = async () => {
  start(true);
  try {
    await manual();
  } catch (e) {
    report.error = e.message;
    $("manual").hidden = false;
    $("status").textContent = `准备失败：${e.message}`;
  }
  $("results").textContent = JSON.stringify(report, null, 2);
};
$("run").onclick = async () => {
  if (!$("offline").checked) {
    $("status").textContent = "请先确认已断网。";
    return;
  }
  start(false);
  document.body.classList.add("running");
  report.visibilityInterruptions = [];
  const visibility = () => {
    if (document.visibilityState !== "visible")
      report.visibilityInterruptions.push(performance.now());
  };
  document.addEventListener("visibilitychange", visibility);
  try {
    $("status").textContent = "正在检查分组和多结果…";
    await open("ten", 10);
    await click("Split a PDF");
    fill(".split-task textarea", "1-3\n4-7\n8-10");
    await click("Create split results");
    await until(() => count() === 4);
    check("three results plus source", true);
    check("source remains active", pageCount(10));
    await click("Open result synthetic-part-02.pdf");
    await until(() => pageCount(4));
    check("second result has four pages", true);
    await click("Organize pages");
    await until(() =>
      doc().querySelector('[aria-label="Select original page 1"]'),
    );
    doc().querySelector('[aria-label="Select original page 1"]').click();
    await click("Rotate selected 90°");
    await click("Apply page changes");
    await until(() => !doc().querySelector(".organize-task"));
    check("editing child retains siblings", count() === 4);
    await click("Open result synthetic.pdf");
    await until(() => pageCount(10));
    await click("Undo Organize pages on synthetic-part-02-organized.pdf");
    await until(() => pageCount(4));
    check("global undo targets edited child", true);
    await click("Undo Split PDF on synthetic.pdf");
    await until(() => count() === 0 && pageCount(10));
    check("undo split restores source", true);
    await click("Redo Split PDF on synthetic.pdf");
    await until(() => count() === 4);
    check("redo restores all results", true);
    await clear();
    await open("ten", 10);
    await click("Split a PDF");
    fill(".split-task select", "each");
    await click("Create split results");
    await until(() => count() === 11);
    check("each-page mode keeps ten results and source", true);
    await click("Open result synthetic-part-10.pdf");
    await until(() => pageCount(1));
    check("last single-page result opens", true);
    await clear();
    await open("hundred", 100);
    await click("Split a PDF");
    fill(".split-task select", "each");
    await sleep(50);
    check(
      "over-limit each-page mode is blocked before generation",
      button("Create split results").disabled,
    );
    fill(".split-task select", "groups");
    fill(".split-task textarea", "1-50\n51-100");
    const started = performance.now();
    await click("Create split results");
    await until(() => count() === 3);
    report.hundredPageSplitMs = Math.round(performance.now() - started);
    check(
      "hundred-page grouped split within 25 seconds",
      report.hundredPageSplitMs <= 25000,
    );
    await clear();
    for (const name of ["credentials", "ordinary"]) {
      await open(name, 2);
      if (name === "ordinary") {
        await click("Create ordinary PDF copy");
        await click("Stay here");
        check(
          "standard conversion cancellation keeps original preview",
          pageCount(2),
        );
        await click("Create ordinary PDF copy");
        await click("Create ordinary copy without standard claims");
        await until(() =>
          doc().body.textContent.includes(
            "This new ordinary PDF does not claim",
          ),
        );
      }
      check(`${name} explicit copy opens`, pageCount(2));
      await click("Split a PDF");
      fill(".split-task textarea", "1\n2");
      await click("Create split results");
      await until(() => count() === 3);
      check(`${name} copy splits offline`, true);
      await clear();
    }
    check("foreground throughout", report.visibilityInterruptions.length === 0);
    await manual();
  } catch (e) {
    report.error = e.message;
    $("status").textContent =
      `自动检查失败：${e.message}。恢复网络后回传即可。`;
  } finally {
    document.removeEventListener("visibilitychange", visibility);
    document.body.classList.remove("running");
    $("manual").hidden = false;
    $("results").textContent = JSON.stringify(report, null, 2);
  }
};
$("send").onclick = async () => {
  if (!report) return;
  report.manualSaveAndOpen = $("saved").checked;
  report.manualContinueChild = $("continued").checked;
  report.manualGlobalHistory = $("history").checked;
  report.manualOrientation = $("orientation").checked;
  try {
    const r = await fetch("/__m0/report", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-m0-token": window.m0Token,
      },
      body: JSON.stringify(report),
    });
    if (!r.ok) throw Error();
    $("status").textContent = "已回传。";
  } catch {
    $("status").textContent = "回传失败，请恢复 Wi-Fi 后重试。";
  }
};
