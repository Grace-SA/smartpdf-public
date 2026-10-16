/* Development-only synthetic photo checks. Manual file bytes are never read here. */
const $ = (id) => document.getElementById(id),
  frame = $("app"),
  files = {};
let report;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const doc = () => frame.contentDocument;
const button = (name) =>
  [...doc().querySelectorAll("button")].find(
    (b) => b.textContent.trim() === name,
  );
async function until(fn, ms = 120000) {
  const end = performance.now() + ms;
  while (!fn()) {
    if (performance.now() > end) throw new Error("等待超时，请回传诊断");
    await sleep(30);
  }
}
async function click(name) {
  await until(() => button(name) && !button(name).disabled);
  button(name).click();
}
function check(name, pass) {
  report.checks.push({ name, pass });
  if (!pass) throw new Error(name);
}
function choose(name) {
  const transfer = new frame.contentWindow.DataTransfer();
  name.forEach((n, i) =>
    transfer.items.add(
      new frame.contentWindow.File(
        [files[n]],
        `synthetic-${i}.${n.split(".").pop()}`,
        { type: n.endsWith("png") ? "image/png" : "image/jpeg" },
      ),
    ),
  );
  const input = doc().querySelector("#photo-files");
  input.files = transfer.files;
  input.dispatchEvent(
    new frame.contentWindow.Event("change", { bubbles: true }),
  );
}
async function add(names) {
  choose(names);
  await sleep(50);
  await until(
    () =>
      button("Apply photos") &&
      !button("Apply photos").disabled &&
      !button("Cancel photo task"),
  );
}
async function apply(count) {
  await click("Apply photos");
  await until(
    () =>
      doc().body.textContent.includes(`Created ${count} pages.`) &&
      !!doc().querySelector(".canvas-host canvas"),
  );
}
async function clear() {
  await click("Clear session");
  await until(() => button("End session"));
  await click("End session");
  await until(() => !doc().querySelector(".canvas-host canvas"));
}
(async () => {
  try {
    for (const name of [
      "red.jpg",
      "green.jpg",
      "blue.jpg",
      "alpha.png",
      "corners.png",
      "benchmark-2mp.jpg",
    ])
      files[name] = await (await fetch(`/__m1/${name}`)).arrayBuffer();
    await until(() =>
      doc()?.body.textContent.includes("Ready for local processing"),
    );
    $("status").textContent =
      "准备完成。关闭网络，勾选确认后点击开始。自动部分约 1–3 分钟；请保持页面前台。";
    $("run").disabled = false;
  } catch {
    $("status").textContent = "准备失败，请保持联网后重新打开此页。";
  }
})();
$("run").onclick = async () => {
  if (!$("offline").checked) {
    $("status").textContent = "请先关闭 Wi-Fi 和蜂窝网络，再勾选确认。";
    return;
  }
  $("run").disabled = true;
  document.body.classList.add("running");
  report = {
    kind: "smartworks-photos-device-check",
    build: window.m0Build,
    userAgent: navigator.userAgent,
    checks: [],
    timings: [],
    visibilityInterruptions: [],
    offlineUserConfirmed: true,
  };
  const visibility = () => {
    if (document.visibilityState !== "visible")
      report.visibilityInterruptions.push(performance.now());
  };
  document.addEventListener("visibilitychange", visibility);
  try {
    await click("Turn Photos into PDF");
    await until(() => doc().querySelector("#photo-files"));
    await add(["red.jpg", "alpha.png", "green.jpg", "blue.jpg", "corners.png"]);
    doc().querySelector('[aria-label="Move image 5 up"]').click();
    doc().querySelector('[aria-label="Rotate image 2"]').click();
    doc().querySelector('[aria-label="Remove image 3"]').click();
    await until(() => doc().querySelectorAll(".photo-list li").length === 4);
    await apply(4);
    check(
      "five photos become four pages",
      doc().body.textContent.includes("Page 1 of 4"),
    );
    await click("Next →");
    await until(() => doc().body.textContent.includes("Page 2 of 4"));
    check("page navigation", true);
    await click("Undo Create Photos PDF");
    await until(() => !doc().querySelector(".canvas-host canvas"));
    check("undo restores empty workspace", true);
    await click("Redo Create Photos PDF");
    await until(() => doc().body.textContent.includes("Page 1 of 4"));
    check("redo restores PDF", true);
    await clear();
    for (let n = 0; n < 22; n++) {
      $("status").textContent =
        `正在测量 10 张照片生成：预热 2 次，正式 ${Math.max(0, n - 1)}/20 次。请保持前台，不锁屏。`;
      check(
        `foreground ${n + 1}`,
        document.visibilityState === "visible" &&
          !report.visibilityInterruptions.length,
      );
      await click("Turn Photos into PDF");
      await until(() => doc().querySelector("#photo-files"));
      await add(Array(10).fill("benchmark-2mp.jpg"));
      const start = performance.now();
      await apply(10);
      if (n >= 2) report.timings.push(performance.now() - start);
      await clear();
    }
    report.p95Ms = [...report.timings].sort((a, b) => a - b)[18];
    check("10 photos P95 <= 20s", report.p95Ms <= 20000);
    await click("Turn Photos into PDF");
    $("status").textContent =
      `自动检查通过，照片生成 P95 ${Math.round(report.p95Ms)} ms。请继续下方手动选择照片、保存并打开 PDF 检查。`;
  } catch (e) {
    report.error = e.message;
    $("status").textContent =
      `自动检查未通过：${e.message}。恢复网络后回传即可。`;
  } finally {
    document.removeEventListener("visibilitychange", visibility);
    document.body.classList.remove("running");
    $("manual").hidden = false;
    $("results").textContent = JSON.stringify(report, null, 2);
  }
};
$("send").onclick = async () => {
  if (!report) return;
  report.manualFilePicker = $("picked").checked;
  report.manualSaveAndOpen = $("saved").checked;
  report.manualOrientation = $("orientation").checked;
  try {
    const response = await fetch("/__m0/report", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-m0-token": window.m0Token,
      },
      body: JSON.stringify(report),
    });
    if (!response.ok) throw new Error();
    $("status").textContent = "已回传。可以回到对话，我会核对结果。";
  } catch {
    $("status").textContent = "回传未成功。请恢复 Wi-Fi 后再次点击回传。";
  }
};
