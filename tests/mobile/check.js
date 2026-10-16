/* Local-only synthetic acceptance harness; never reads a user-selected file. */
const byId = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const frame = byId("app");
let report;
const files = {};
async function until(condition, timeout = 30000) {
  const deadline = performance.now() + timeout;
  while (!condition()) {
    if (performance.now() > deadline)
      throw new Error("Timed out waiting for preview");
    await sleep(50);
  }
}
function doc() {
  return frame.contentDocument;
}
function button(name) {
  return [...doc().querySelectorAll("button")].find((b) =>
    b.textContent.includes(name),
  );
}
async function open(name) {
  await until(() => !doc().querySelector("#pdf-file").disabled);
  const transfer = new frame.contentWindow.DataTransfer();
  transfer.items.add(
    new frame.contentWindow.File([files[name]], `${name}.pdf`, {
      type: "application/pdf",
    }),
  );
  const input = doc().querySelector("#pdf-file");
  input.files = transfer.files;
  input.dispatchEvent(
    new frame.contentWindow.Event("change", { bubbles: true }),
  );
  await sleep(60);
  await until(() => !input.disabled);
}
(async () => {
  try {
    for (const name of ["plain", "form", "scan", "benchmark-10p-5mib"])
      files[name] = await (await fetch(`/__m0/${name}.pdf`)).arrayBuffer();
    byId("sample").href = URL.createObjectURL(
      new Blob([files.plain], { type: "application/pdf" }),
    );
    await until(() =>
      doc()?.body.textContent.includes("Ready for local processing"),
    );
    const enginePath = Object.keys(window.m0Build).find((path) =>
      /^assets\/engine-[\w-]+\.js$/.test(path),
    );
    const diagnosticScript = doc().createElement("script");
    diagnosticScript.type = "module";
    diagnosticScript.src = `/__m0/diagnostic.js?engine=${encodeURIComponent("/" + enginePath)}`;
    doc().head.append(diagnosticScript);
    await until(() => frame.contentWindow.m0Diagnose);
    byId("status").textContent =
      "① 准备完成。② 关闭网络并勾选确认框。③ 点击“开始离线测试”。";
    if (/MicroMessenger/i.test(navigator.userAgent))
      byId("status").textContent =
        "当前是微信内置浏览器。请直接启动 Chrome，并把本页完整地址粘贴到 Chrome 地址栏，再开始正式手机验收。";
    byId("run").disabled = false;
  } catch (error) {
    byId("status").textContent = `准备未完成：${error.message}`;
  }
})();
byId("run").onclick = async () => {
  if (!byId("offline").checked) {
    byId("status").textContent = "请先关闭网络并勾选确认。";
    return;
  }
  byId("run").disabled = true;
  document.body.classList.add("running");
  report = {
    kind: "smartworks-synthetic-device-check",
    harnessVersion: "visible-frame-2026-10-06",
    build: window.m0Build,
    declaredDevice: "iPhone 12 Pro Max / iOS 18.7.7",
    userAgent: navigator.userAgent,
    platform: navigator.platform,
    hardwareConcurrency: navigator.hardwareConcurrency ?? null,
    deviceMemoryGiB: navigator.deviceMemory ?? null,
    screen: {
      width: screen.width,
      height: screen.height,
      dpr: devicePixelRatio,
    },
    startedAt: new Date().toISOString(),
    offlineUserConfirmed: true,
    checks: [],
    timings: [],
    visibilitySamples: [],
    animationFrameWaits: [],
    visibilityInterruptions: [],
  };
  const noteVisibility = () => {
    if (
      document.visibilityState !== "visible" ||
      doc().visibilityState !== "visible"
    )
      report.visibilityInterruptions.push(performance.now());
  };
  document.addEventListener("visibilitychange", noteVisibility);
  doc().addEventListener("visibilitychange", noteVisibility);
  const check = (name, pass) => {
    report.checks.push({ name, pass });
    if (!pass) throw new Error(name);
  };
  // Diagnostics exist only in this opt-in synthetic harness, not the product.
  // Stop collecting before the user manually chooses any document.
  report.diagnostics = [];
  let collecting = true;
  let delayReading = false;
  const w = frame.contentWindow;
  const record = (kind, value) => {
    if (kind === "animation frame wait ms") {
      if (collecting && report.animationFrameWaits.length < 128)
        report.animationFrameWaits.push(value);
      return;
    }
    if (collecting && report.diagnostics.length < 24)
      report.diagnostics.push({ kind, detail: String(value).slice(0, 600) });
  };
  const rejected = (event) =>
    record(
      "unhandled rejection",
      `${event.reason?.name}: ${event.reason?.message}`,
    );
  const failed = (event) => record("page exception", event.message);
  w.addEventListener("unhandledrejection", rejected);
  w.addEventListener("error", failed);
  const restoreInstrumentation = w.m0InstallDiagnostics(
    record,
    () => delayReading,
  );
  const stages = new window.MutationObserver(() => {
    const stage = doc().querySelector(".busy p")?.textContent;
    if (stage && stage !== report.lastStage) {
      report.lastStage = stage;
      record("stage", stage);
    }
  });
  stages.observe(doc().body, {
    childList: true,
    subtree: true,
    characterData: true,
  });
  try {
    byId("status").textContent = "正在验证打开、翻页和失败恢复…";
    await open("plain");
    check("plain preview", !!doc().querySelector("canvas"));
    button("Next").click();
    await until(() => doc().body.textContent.includes("Page 2 of 2"));
    check("next page", true);
    await open("form");
    check(
      "form rejected without replacing prior page",
      !!doc().querySelector('[role="alert"]') &&
        doc().body.textContent.includes("Page 2 of 2"),
    );
    byId("status").textContent = "正在检查取消响应和原页面保护…";
    delayReading = true;
    const pending = open("plain");
    await until(() => button("Cancel"));
    const cancelStart = performance.now();
    button("Cancel").click();
    await until(() =>
      doc().querySelector('[role="alert"]')?.textContent.includes("Cancelled"),
    );
    report.cancelMs = performance.now() - cancelStart;
    check(
      "cancel response <= 1000ms (controlled pending read)",
      report.cancelMs <= 1000,
    );
    await pending;
    await sleep(1600);
    check(
      "cancel prevents late replacement",
      doc().body.textContent.includes("Page 2 of 2"),
    );
    delayReading = false;
    button("Clear session").click();
    await until(() => !doc().querySelector("canvas"));
    await open("scan");
    check("scan preview", !!doc().querySelector("canvas"));
    button("Clear session").click();
    for (let i = 0; i < 10; i++) {
      byId("status").textContent = `正在检查打开与清除 ${i + 1}/10…`;
      await open("plain");
      check(`cycle ${i + 1} preview`, !!doc().querySelector("canvas"));
      button("Clear session").click();
      await until(() => !doc().querySelector("canvas"));
    }
    for (let i = 0; i < 22; i++) {
      byId("status").textContent = `正在测量性能 ${Math.max(0, i - 1)}/20…`;
      const rect = frame.getBoundingClientRect();
      const visibleHeight = Math.max(
        0,
        Math.min(rect.bottom, window.innerHeight) - Math.max(0, rect.top),
      );
      const visible =
        document.visibilityState === "visible" &&
        doc().visibilityState === "visible" &&
        visibleHeight >= 150;
      report.visibilitySamples.push({ visible, visibleHeight });
      if (!visible || report.visibilityInterruptions.length)
        throw new Error(
          "测试页面需保持前台且预览可见；本轮计时无效，请重新打开测试",
        );
      const start = performance.now();
      await open("benchmark-10p-5mib");
      check(
        `benchmark ${i + 1}`,
        doc().body.textContent.includes("Page 1 of 10"),
      );
      if (i >= 2) report.timings.push(performance.now() - start);
      button("Clear session").click();
    }
    report.p95Ms = [...report.timings].sort((a, b) => a - b)[18];
    if (report.visibilityInterruptions.length)
      throw new Error("测试期间页面离开前台，本轮计时无效，请保持本页前台重试");
    check("P1 import p95 <= 4000ms", report.p95Ms <= 4000);
    await open("plain");
    byId("status").textContent =
      `✓ 自动测试通过：打开、翻页、拒绝恢复、扫描预览、10 次清除及 20 次速度测试均通过（P95 ${Math.round(report.p95Ms)} ms）。请检查横竖屏及文件选择，然后恢复 Wi-Fi 回传结果。`;
  } catch (error) {
    report.error = error.message;
    // Retry the synthetic fixture without any constructor instrumentation to
    // distinguish a product failure from interference by the test harness.
    restoreInstrumentation();
    if (
      error.message === "plain preview" ||
      error.message === "scan preview" ||
      /^benchmark /.test(error.message)
    ) {
      report.renderDiagnostic = await w.m0Diagnose(
        new w.File([files.plain], "plain.pdf", { type: "application/pdf" }),
      );
      report.renderDiagnostic.instrumentationDisabled = true;
    }
    report.appStatus =
      doc()?.querySelector('[role="alert"]')?.textContent ?? null;
    report.inputState = {
      disabled: doc()?.querySelector("#pdf-file")?.disabled,
      selectedSyntheticFile:
        doc()?.querySelector("#pdf-file")?.files?.[0]?.name ?? null,
    };
    byId("status").textContent =
      `测试发现问题：${error.message}。${report.appStatus ?? ""} 请恢复 Wi-Fi 回传结果，我会继续修复。`;
  } finally {
    collecting = false;
    stages.disconnect();
    w.removeEventListener("unhandledrejection", rejected);
    w.removeEventListener("error", failed);
    w.m0DisposeDiagnostic();
    restoreInstrumentation();
    document.body.classList.remove("running");
    document.removeEventListener("visibilitychange", noteVisibility);
    doc().removeEventListener("visibilitychange", noteVisibility);
    byId("status").scrollIntoView({ block: "start" });
  }
  byId("results").textContent = JSON.stringify(report, null, 2);
  byId("send").disabled = false;
};
byId("send").onclick = async () => {
  report.manualOrientation = byId("orientation").checked;
  report.manualFilePicker = byId("picker").checked;
  try {
    const response = await fetch("/__m0/report", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-M0-Token": window.m0Token,
      },
      body: JSON.stringify(report),
    });
    if (!response.ok) throw new Error("Network not ready");
    byId("status").textContent = "结果已回传电脑，可以告诉我继续核对验收。";
  } catch {
    byId("status").textContent = "尚未回传，请连接与电脑相同的 Wi-Fi 后重试。";
  }
};
