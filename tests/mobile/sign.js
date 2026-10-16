// Manual acceptance metadata only. No file input, names, signature data or storage.
document.getElementById("send").onclick = async () => {
  const button = document.getElementById("send"),
    status = document.getElementById("status");
  button.disabled = true;
  try {
    const response = await fetch("/__m0/report", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-M0-Token": window.m5Token,
      },
      body: JSON.stringify({
        kind: "smartworks-sign-device-check",
        mode: "manual-only",
        build: window.m5Build,
        userAgent: navigator.userAgent,
        at: new Date().toISOString(),
        checks: [...document.querySelectorAll("[data-check]")].map((el) => ({
          name: el.dataset.check,
          pass: el.checked,
        })),
      }),
    });
    if (!response.ok) throw Error();
    status.textContent =
      "已回传。未通过的项目请在聊天中描述；本页不会自动判定整体验收通过。";
  } catch {
    status.textContent =
      "回传失败。请恢复与电脑相同的 Wi-Fi 后重试，勾选仍保留。";
  } finally {
    button.disabled = false;
  }
};
