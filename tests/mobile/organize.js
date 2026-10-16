/* Development-only synthetic M3 harness. Never collects user document data. */
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
async function prepareManual() {
  await open("ten", 10);
  await click("Organize pages");
  await until(() => doc().querySelector(".organize-row"));
  $("manual").hidden = false;
  $("status").textContent =
    "十页练习文件已打开，页面整理已展开。请按下方中文步骤操作，无需再选 PDF。";
}
async function until(fn) {
  const end = performance.now() + 120000;
  while (!fn()) {
    if (performance.now() > end) throw Error("等待超时，请恢复网络回传诊断");
    await sleep(30);
  }
}
async function click(name) {
  await until(() => button(name) && !button(name).disabled);
  button(name).click();
  // Organize opens only after an asynchronous compatibility preflight.
  // A clickable button does not mean the draft rows have mounted yet.
  if (name === "Organize pages")
    await until(() => checkbox(1) || doc().querySelector(".organize-row"));
}
function check(name, pass) {
  report.checks.push({ name, pass });
  if (!pass) throw Error(name);
}
function checkbox(n) {
  return doc().querySelector(`[aria-label="Select original page ${n}"]`);
}
async function select(n) {
  await until(() => checkbox(n));
  if (!checkbox(n).checked) checkbox(n).click();
}
async function scroll(bottom) {
  const v = doc().querySelector(".organize-viewport");
  v.scrollTop = bottom ? v.scrollHeight : 0;
  await sleep(100);
}
async function open(name, count) {
  const w = frame.contentWindow,
    t = new w.DataTransfer();
  t.items.add(
    new w.File([files[name]], "synthetic.pdf", { type: "application/pdf" }),
  );
  const input = doc().querySelector("#pdf-file");
  input.files = t.files;
  input.dispatchEvent(new w.Event("change", { bubbles: true }));
  await until(() => doc().body.textContent.includes(`Page 1 of ${count}`));
}
(async () => {
  try {
    for (const name of ["ten", "hundred", "linked"]) {
      const r = await fetch(`/__m3/${name}.pdf`);
      if (!r.ok) throw Error("样本未就绪");
      files[name] = await r.arrayBuffer();
    }
    await until(() =>
      doc()?.body.textContent.includes("Ready for local processing"),
    );
    $("status").textContent =
      "准备完成。断开 Wi-Fi 和蜂窝网络，勾选确认后开始。";
    $("run").disabled = false;
    $("manual-only").disabled = false;
  } catch (e) {
    $("status").textContent = `准备失败：${e.message}`;
  }
})();
$("manual-only").onclick = async () => {
  $("manual-only").disabled = true;
  $("run").disabled = true;
  report = {
    kind: "smartworks-organize-device-check",
    harnessVersion: "m3-usability-3",
    build: window.m0Build,
    userAgent: navigator.userAgent,
    checks: [],
    manualOnly: true,
  };
  try {
    await prepareManual();
  } catch (e) {
    report.error = e.message;
    $("status").textContent = `练习文件准备失败：${e.message}`;
    $("manual").hidden = false;
  }
  $("results").textContent = JSON.stringify(report, null, 2);
};
$("run").onclick = async () => {
  if (!$("offline").checked) {
    $("status").textContent = "请先确认已断网。";
    return;
  }
  $("run").disabled = true;
  $("manual-only").disabled = true;
  document.body.classList.add("running");
  report = {
    kind: "smartworks-organize-device-check",
    harnessVersion: "m3-usability-3",
    build: window.m0Build,
    userAgent: navigator.userAgent,
    checks: [],
    offlineUserConfirmed: true,
    visibilityInterruptions: [],
  };
  const visibility = () => {
    if (document.visibilityState !== "visible")
      report.visibilityInterruptions.push(performance.now());
  };
  document.addEventListener("visibilitychange", visibility);
  try {
    $("status").textContent = "正在检查十页整理、撤销和重做…";
    report.currentStep = "Ten-page organization";
    await open("ten", 10);
    await click("Organize pages");
    check("no implicit page selection", !checkbox(1).checked);
    await select(1);
    await click("Rotate selected 90°");
    await click("Undo draft change");
    check(
      "draft undo restores rotation",
      checkbox(1)
        .closest(".organize-row")
        .textContent.includes("0° added rotation"),
    );
    await click("Redo draft change");
    check(
      "draft redo restores rotation",
      checkbox(1)
        .closest(".organize-row")
        .textContent.includes("90° added rotation"),
    );
    await click("Undo draft change");
    await click("Clear selection");
    await scroll(true);
    await select(10);
    const id = checkbox(10).closest(".organize-row").dataset.pageId;
    await click("Move selected to position");
    await click("Clear selection");
    await scroll(true);
    await select(8);
    await select(9);
    await click("Delete selected pages");
    await scroll(false);
    await select(4);
    await click("Rotate selected 90°");
    const started = performance.now();
    await click("Apply page changes");
    await until(
      () =>
        doc().body.textContent.includes("Page 1 of 8") &&
        !doc().querySelector(".organize-task"),
    );
    report.applyMs = Math.round(performance.now() - started);
    check(
      "ten pages become eight; original page ten is first",
      doc().body.textContent.includes("Original page 10"),
    );
    await click("Organize pages");
    check(
      "page identity survives Apply",
      doc().querySelector(".organize-row").dataset.pageId === id,
    );
    await click("Cancel page changes");
    await click("Undo Organize pages");
    await until(() => doc().body.textContent.includes("Page 1 of 10"));
    check("undo restores ten pages", true);
    await click("Redo Organize pages");
    await until(() => doc().body.textContent.includes("Page 1 of 8"));
    check("redo restores eight pages", true);
    await click("Organize pages");
    await click("Select all pages");
    await click("Delete selected pages");
    check(
      "cannot delete every page",
      doc().body.textContent.includes("Keep at least one page"),
    );
    await click("Cancel page changes");
    await click("Organize pages");
    await select(1);
    await click("Rotate selected 90°");
    await click("Combine PDFs");
    await until(() => doc().querySelector("dialog[open]"));
    check(
      "switching tasks protects draft",
      doc().body.textContent.includes("Apply this page draft"),
    );
    await click("Stay here");
    await click("Cancel page changes");
    check(
      "cancel leaves eight-page result",
      doc().body.textContent.includes("Page 1 of 8"),
    );
    await click("Clear session");
    await click("End session");
    await until(() => !doc().querySelector(".canvas-host canvas"));
    $("status").textContent = "正在检查百页缩略图滚动…";
    report.currentStep = "Hundred-page virtual thumbnails";
    await open("hundred", 100);
    await click("Organize pages");
    await select(1);
    await until(() => doc().querySelector(".organize-thumbnail canvas"));
    check(
      "visible thumbnails bounded",
      doc().querySelectorAll(".organize-row").length <= 8,
    );
    await scroll(true);
    await until(() => checkbox(100));
    check(
      "last page reachable without rendering all pages",
      doc().querySelectorAll(".organize-thumbnail canvas").length <= 8,
    );
    await scroll(false);
    await until(() => checkbox(1));
    check("offscreen selection retained", checkbox(1).checked);
    await click("Cancel page changes");
    await click("Clear session");
    await until(() => !doc().querySelector(".canvas-host canvas"));
    await open("linked", 2);
    await click("Organize pages");
    await select(1);
    await click("Delete selected pages");
    await click("Apply page changes");
    await until(() => doc().querySelector('.organize-task [role="alert"]'));
    check(
      "referenced deletion requires explicit choice",
      doc().body.textContent.includes("still refers"),
    );
    doc().querySelector(".organize-deletion-policy input").click();
    await click("Apply page changes");
    await until(() => !doc().querySelector(".organize-task"));
    check(
      "explicit associated deletion succeeds",
      doc().body.textContent.includes("Page 1 of 1"),
    );
    check("foreground throughout", report.visibilityInterruptions.length === 0);
    await click("Clear session");
    await click("End session");
    await until(() => !doc().querySelector(".canvas-host canvas"));
    await prepareManual();
  } catch (e) {
    report.error = e.message;
    report.syntheticAlerts = [...doc().querySelectorAll('[role="alert"]')].map(
      (e) => e.textContent,
    );
    $("status").textContent = `自动检查失败：${e.message}。恢复网络直接回传。`;
  } finally {
    document.removeEventListener("visibilitychange", visibility);
    document.body.classList.remove("running");
    $("manual").hidden = false;
    $("results").textContent = JSON.stringify(report, null, 2);
  }
};
$("send").onclick = async () => {
  if (!report) return;
  report.manualTouchEdit = $("edited").checked;
  report.manualSaveAndOpen = $("saved").checked;
  report.manualOrientation = $("orientation").checked;
  report.manualDraftConfirmation = $("confirmed").checked;
  report.manualPageJump = $("jumped").checked;
  report.manualRangeSelection = $("ranged").checked;
  report.manualEnlargedPreview = $("enlarged").checked;
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
