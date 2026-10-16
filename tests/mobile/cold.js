const byId = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let report;
async function until(check) {
  const start = performance.now();
  while (!check()) {
    if (performance.now() - start > 30000) throw new Error("页面准备超时");
    await sleep(25);
  }
}
byId("run").onclick = async () => {
  byId("run").disabled = true;
  document.body.classList.add("running");
  report = {
    kind: "smartworks-mobile-cold",
    harnessVersion: "visible-frame-safe-port-2026-10-06",
    build: window.m0Build,
    userAgent: navigator.userAgent,
    startedAt: new Date().toISOString(),
    samples: [],
    network:
      "Server-paced shared 10Mbps, 64KiB maximum burst, gzip and 100ms response delay; no-store; physical Wi-Fi/RTT not controlled",
  };
  try {
    for (let i = 0; i < 3; i++) {
      byId("status").textContent = `正在检查第 ${i + 1}/3 次加载…`;
      const frame = document.createElement("iframe");
      frame.title = "加载检查预览";
      const start = performance.now();
      frame.src = `/?cold=${Date.now()}`;
      byId("frames").replaceChildren(frame);
      await until(() =>
        [...(frame.contentDocument?.querySelectorAll("h2") ?? [])].some(
          (h) => h.textContent === "Your PDF, just here.",
        ),
      );
      const disclosure = frame.contentDocument.querySelector("summary");
      disclosure.click();
      if (!disclosure.parentElement.open) throw new Error("页面尚不可操作");
      const shellMs = performance.now() - start;
      await until(() =>
        frame.contentDocument?.body.textContent.includes(
          "Ready for local processing",
        ),
      );
      report.samples.push({ shellMs, readyMs: performance.now() - start });
    }
    report.pass = report.samples.every((sample) => sample.shellMs <= 5000);
    byId("status").textContent = report.pass
      ? "✓ 三次页面加载均在 5 秒内可操作。请回传结果。"
      : "加载速度未达到 5 秒目标。请回传结果，我会继续排查。";
  } catch (error) {
    report.error = error.message;
    report.pass = false;
    byId("status").textContent = `${error.message}。请回传结果。`;
  } finally {
    document.body.classList.remove("running");
    byId("status").scrollIntoView({ block: "start" });
  }
  byId("results").textContent = JSON.stringify(report, null, 2);
  byId("send").disabled = false;
};
byId("send").onclick = async () => {
  try {
    const response = await fetch("/__m0/report", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-M0-Token": window.m0Token,
      },
      body: JSON.stringify(report),
    });
    if (!response.ok) throw new Error("回传未成功");
    byId("status").textContent = "结果已回传电脑。";
  } catch {
    byId("status").textContent = "请保持同一 Wi-Fi，再点击回传。";
  }
};
