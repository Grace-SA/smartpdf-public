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
    const error = doc()?.querySelector(".photo-list [role=alert]");
    if (error) throw new Error(error.textContent);
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
        {
          type: n.endsWith("heic")
            ? "image/heic"
            : n.endsWith("png")
              ? "image/png"
              : "image/jpeg",
        },
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
      "synthetic.heic",
      "synthetic-12mp.heic",
      "synthetic-icc.heic",
      "synthetic-rotated.heic",
    ])
      files[name] = await (await fetch(`/__m1/${name}`)).arrayBuffer();
    await until(() =>
      doc()?.body.textContent.includes("Ready for local processing"),
    );
    $("status").textContent =
      "准备完成。关闭网络，勾选确认后点击开始。自动部分约 1–3 分钟；请保持页面前台。";
    $("run").disabled = false;
    $("manual-only").disabled = false;
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
    kind: "smartworks-heic-device-check",
    build: window.m0Build,
    harnessVersion: "heic-hdr-v3",
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
    for (const [name, batch] of [
      [
        "20 mixed JPEG PNG HEIC",
        [
          ...Array(16).fill("synthetic.heic"),
          "synthetic-icc.heic",
          "synthetic-rotated.heic",
          "red.jpg",
          "alpha.png",
        ],
      ],
      ["20 twelve-megapixel HEIC", Array(20).fill("synthetic-12mp.heic")],
    ]) {
      $("status").textContent =
        `正在测试 ${name}：逐张解码并生成 20 页 PDF。请保持前台。`;
      await click("Turn Photos into PDF");
      await until(() => doc().querySelector("#photo-files"));
      const start = performance.now();
      await add(batch);
      await apply(20);
      check(name, doc().body.textContent.includes("Page 1 of 20"));
      report.timings.push({
        name,
        elapsedMs: Math.round(performance.now() - start),
      });
      await clear();
    }
    check("foreground throughout", !report.visibilityInterruptions.length);
    await click("Turn Photos into PDF");
    $("status").textContent =
      "自动检查通过：混合 20 张、20 张 12MP HEIC 均已生成。接下来在下方选择自己的 HEIC，保存 PDF 并打开核对。";
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
  report.manualFilesRoute = $("files-route").checked;
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

$("manual-only").onclick = async () => {
  $("run").disabled = true;
  $("manual-only").disabled = true;
  report = {
    kind: "smartworks-heic-device-check",
    harnessVersion: "heic-hdr-v3",
    build: window.m0Build,
    userAgent: navigator.userAgent,
    checks: [],
    timings: [],
    manualOnly: true,
    offlineUserConfirmed: false,
  };
  try {
    await click("Turn Photos into PDF");
    await until(() => doc().querySelector("#photo-browse-files"));
    $("status").textContent =
      "请在下面的应用点击 Browse Files，选原始 HEIC，生成、保存并打开核对，然后勾选并回传。无需重跑自动测试。";
  } catch (e) {
    report.error = e.message;
    $("status").textContent = "入口准备失败，请回传诊断。";
  }
  $("manual").hidden = false;
  $("results").textContent = JSON.stringify(report, null, 2);
};
