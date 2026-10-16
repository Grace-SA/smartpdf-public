/* Development-only synthetic M2 checks; personal input bytes are never collected. */
const $ = (id) => document.getElementById(id),
  frame = $("app"),
  files = {};
let report;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms)),
  doc = () => frame.contentDocument;
const button = (name) =>
  [...doc().querySelectorAll("button")].find(
    (b) => b.textContent.trim() === name,
  );
async function until(fn, ms = 120000) {
  const end = performance.now() + ms;
  while (!fn()) {
    if (performance.now() > end) throw Error("等待超时，请回传诊断");
    await sleep(30);
  }
}
async function click(name) {
  await until(() => button(name) && !button(name).disabled);
  button(name).click();
}
function check(name, pass) {
  report.checks.push({ name, pass });
  if (!pass) throw Error(name);
}
async function add(names) {
  report.currentStep = `Read synthetic inputs: ${names.join(", ")}`;
  $("status").textContent = "正在读取合成样本并检查结构，请保持页面在前台。";
  const w = frame.contentWindow,
    t = new w.DataTransfer();
  names.forEach((name, i) =>
    t.items.add(
      new w.File([files[name]], `synthetic-${i}.pdf`, {
        type: "application/pdf",
      }),
    ),
  );
  const input = doc().querySelector("#combine-files");
  input.files = t.files;
  input.dispatchEvent(new w.Event("change", { bubbles: true }));
  await until(
    () =>
      doc().querySelectorAll(".photo-list li").length === names.length &&
      !button("Cancel combine task"),
  );
  await until(
    () => button("Apply combine") && !button("Apply combine").disabled,
  );
}
async function apply(pages) {
  report.currentStep = `Combine and preview ${pages} synthetic pages`;
  $("status").textContent = `正在合并并预览 ${pages} 页合成样本，请稍候。`;
  await click("Apply combine");
  await until(
    () =>
      doc().body.textContent.includes(`Combined ${pages} pages.`) &&
      !!doc().querySelector(".canvas-host canvas"),
  );
}
async function clear() {
  await click("Clear session");
  await until(() => button("Discard changes") || button("End session"));
  if (button("Discard changes")) await click("Discard changes");
  await click("End session");
  await until(() => !doc().querySelector(".canvas-host canvas"));
}
(async () => {
  try {
    for (const n of [
      "a",
      "b",
      "c",
      "navigation-a",
      "navigation-b",
      "layer-on",
      "layer-off",
      "tag-a",
      "tag-b",
      "ordinary-tagged-link",
      "ordinary-comments",
      "ordinary-scan",
      "ordinary-wrapped-image",
      "indexed-artifact",
      "unconfigured-layer",
      "empty-form",
      "final-jpeg",
      "final-jpeg-overlimit",
      "final-form",
      "final-attachment",
      "final-tags",
      "final-color",
      "final-stream-scan",
      "final-inline",
      ...Array.from({ length: 5 }, (_, i) => `benchmark-${i + 1}`),
    ]) {
      const response = await fetch(`/__m2/${n}.pdf`);
      if (!response.ok) throw Error("样本加载失败");
      files[n] = await response.arrayBuffer();
    }
    await until(() =>
      doc()?.body.textContent.includes("Ready for local processing"),
    );
    $("status").textContent =
      "准备完成。关闭 Wi-Fi 与蜂窝网络，勾选确认，再点击开始离线测试。";
    $("run").disabled = false;
  } catch (e) {
    $("status").textContent = `准备失败：${e.message}。恢复网络后重新打开。`;
  }
})();
$("run").onclick = async () => {
  if (!$("offline").checked) {
    $("status").textContent = "请先确认已断网。";
    return;
  }
  $("run").disabled = true;
  document.body.classList.add("running");
  report = {
    kind: "smartworks-combine-device-check",
    harnessVersion: "m2-resource-fix-1",
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
    await click("Combine PDFs");
    await until(() => doc().querySelector("#combine-files"));
    await add(["a", "b", "c"]);
    await click("↓ Down"); // move first file after B
    const move = [...doc().querySelectorAll("button")].find(
      (b) => b.getAttribute("aria-label") === "Move PDF 3 up",
    );
    move.click();
    await sleep(50);
    await apply(6);
    check(
      "three files become six pages",
      doc().body.textContent.includes("Page 1 of 6"),
    );
    check(
      "reordered first page",
      doc().querySelector(".page-text").textContent.includes("B-1"),
    );
    await click("Undo Combine PDFs");
    await until(() => !doc().querySelector(".canvas-host canvas"));
    check("undo", true);
    await click("Redo Combine PDFs");
    await until(() => doc().body.textContent.includes("Page 1 of 6"));
    check("redo", true);
    await clear();
    await click("Combine PDFs");
    await until(() => doc().querySelector("#combine-files"));
    await add(["navigation-b", "navigation-a", "navigation-b"]);
    await apply(9);
    check(
      "navigation PDFs accepted and merged offline",
      doc().body.textContent.includes("Page 1 of 9"),
    );
    check(
      "navigation first page retained",
      doc().querySelector(".page-text").textContent.includes("B page 1"),
    );
    await clear();
    await click("Combine PDFs");
    await until(() => doc().querySelector("#combine-files"));
    await add(["layer-off", "tag-a", "layer-on", "tag-b"]);
    await apply(4);
    check(
      "layers and tags accepted and merged offline",
      doc().body.textContent.includes("Page 1 of 4"),
    );
    await clear();
    await click("Combine PDFs");
    await until(() => doc().querySelector("#combine-files"));
    await add([
      "ordinary-scan",
      "ordinary-tagged-link",
      "ordinary-comments",
      "ordinary-wrapped-image",
    ]);
    await apply(4);
    check(
      "ordinary scan, tagged link, comments and wrapped JPEG merge offline",
      doc().body.textContent.includes("Page 1 of 4"),
    );
    await clear();
    await click("Combine PDFs");
    await until(() => doc().querySelector("#combine-files"));
    await add([
      "indexed-artifact",
      "unconfigured-layer",
      "empty-form",
      "layer-off",
    ]);
    await apply(4);
    check(
      "closing batch: indexed tags, visible layers and empty form settings merge offline",
      doc().body.textContent.includes("Page 1 of 4"),
    );
    await clear();
    await click("Combine PDFs");
    await until(() => doc().querySelector("#combine-files"));
    await add(["final-jpeg", "final-form", "final-attachment", "final-tags"]);
    await apply(4);
    check(
      "24MP JPEG budget, flat form, invoice attachment and incomplete tag graph merge offline",
      doc().body.textContent.includes("Page 1 of 4"),
    );
    {
      report.currentStep =
        "Reject understated 30 MP JPEG without changing the document";
      const w = frame.contentWindow,
        transfer = new w.DataTransfer();
      transfer.items.add(
        new w.File([files["final-jpeg-overlimit"]], "synthetic-overlimit.pdf", {
          type: "application/pdf",
        }),
      );
      const input = doc().querySelector("#combine-files");
      input.files = transfer.files;
      input.dispatchEvent(new w.Event("change", { bubbles: true }));
      await until(
        () =>
          doc().querySelectorAll(".photo-list li").length === 2 &&
          !button("Cancel combine task"),
      );
      check(
        "understated wrapped 30MP JPEG rejected; previous output retained",
        button("Apply combine").disabled &&
          doc().body.textContent.includes("Page 1 of 4") &&
          !!doc().querySelector(".canvas-host canvas"),
      );
    }
    await clear();
    await click("Combine PDFs");
    await until(() => doc().querySelector("#combine-files"));
    await add(["final-color", "final-color"]);
    await apply(2);
    check(
      "matching output colour profiles merge offline",
      doc().body.textContent.includes("Page 1 of 2"),
    );
    await clear();
    await click("Combine PDFs");
    await until(() => doc().querySelector("#combine-files"));
    await add(["final-stream-scan", "final-inline", "final-attachment"]);
    await apply(14);
    check(
      "144MiB streamed scans and compressed inline images merge offline",
      doc().body.textContent.includes("Page 1 of 14"),
    );
    await clear();
    for (let n = 0; n < 22; n++) {
      $("status").textContent =
        `正在测试 100 页合并：预热 2 次，正式 ${Math.max(0, n - 1)}/20 次。请保持前台，不锁屏。`;
      check(
        `foreground ${n + 1}`,
        document.visibilityState === "visible" &&
          !report.visibilityInterruptions.length,
      );
      await click("Combine PDFs");
      await until(() => doc().querySelector("#combine-files"));
      await add(Array.from({ length: 5 }, (_, i) => `benchmark-${i + 1}`));
      const started = performance.now();
      await apply(100);
      if (n >= 2) report.timings.push(performance.now() - started);
      await clear();
    }
    report.p95Ms = [...report.timings].sort((a, b) => a - b)[18];
    check("100 pages P95 <= 25s", report.p95Ms <= 25000);
    await click("Combine PDFs");
    $("status").textContent =
      `自动检查通过，P95 ${Math.round(report.p95Ms)} ms。请恢复网络，完成手动选文件、保存后打开及确认框检查，再回传。`;
  } catch (e) {
    report.error = e.message;
    report.syntheticAlerts = [...doc().querySelectorAll('[role="alert"]')].map(
      (n) => n.textContent,
    );
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
  report.manualConfirmations = $("confirmed").checked;
  try {
    const response = await fetch("/__m0/report", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-m0-token": window.m0Token,
      },
      body: JSON.stringify(report),
    });
    if (!response.ok) throw Error();
    $("status").textContent = "已回传。可以回到对话，我会核对结果。";
  } catch {
    $("status").textContent = "回传失败，请恢复 Wi-Fi 后重试。";
  }
};
