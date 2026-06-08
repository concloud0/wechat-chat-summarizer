const form = document.querySelector("#summary-form");
const fileInput = document.querySelector("#chat-file");
const fileName = document.querySelector("#file-name");
const previewTitle = document.querySelector("#preview-title");
const preview = document.querySelector("#preview");
const rawOutput = document.querySelector("#raw-output");
const emptyState = document.querySelector("#empty-state");
const copyButton = document.querySelector("#copy-button");
const downloadButton = document.querySelector("#download-button");
const shutdownButton = document.querySelector("#shutdown-button");
const messageCount = document.querySelector("#message-count");
const speakerCount = document.querySelector("#speaker-count");
const encodingUsed = document.querySelector("#encoding-used");
const ignoredLines = document.querySelector("#ignored-lines");
const formatSelect = document.querySelector("#format-select");
const engineSelect = document.querySelector("#engine-select");
const deepseekFields = document.querySelector("#deepseek-fields");
const privacyTitle = document.querySelector("#privacy-title");
const privacyText = document.querySelector("#privacy-text");
const sourceSelect = document.querySelector("#source-select");
const fileSource = document.querySelector("#file-source");
const wechatSource = document.querySelector("#wechat-source");
const dateFromInput = document.querySelector("input[name='date_from']");
const dateToInput = document.querySelector("input[name='date_to']");
const wechatStatusButton = document.querySelector("#wechat-status-button");
const wechatSessionsButton = document.querySelector("#wechat-sessions-button");
const wechatStatus = document.querySelector("#wechat-status");
const wechatSessionSelect = document.querySelector("#wechat-session-select");
const wechatSessionLimit = document.querySelector("#wechat-session-limit");

let latestReport = "";
let latestDownloadName = "wechat_summary.md";

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  fileName.textContent = file ? `${file.name} (${formatBytes(file.size)})` : "支持 txt、csv、log 等文本文件";
});

engineSelect.addEventListener("change", () => {
  updateEngineMode();
  updateSourceMode();
});
sourceSelect.addEventListener("change", updateSourceMode);
dateFromInput.addEventListener("change", syncDateBounds);
dateToInput.addEventListener("change", syncDateBounds);
wechatStatusButton.addEventListener("click", checkWechatStatus);
wechatSessionsButton.addEventListener("click", loadWechatSessions);
shutdownButton.addEventListener("click", shutdownApp);
updateEngineMode();
updateSourceMode();
syncDateBounds();

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitButton = form.querySelector("button[type='submit']");
  submitButton.disabled = true;
  submitButton.textContent = sourceSelect.value === "wechat" ? "导出中..." : "生成中...";

  try {
    const response =
      sourceSelect.value === "wechat"
        ? await summarizeWechat()
        : await summarizeFile();
    const data = await response.json();
    if (!data.ok) {
      throw new Error(data.error || "生成失败");
    }
    renderResult(data);
  } catch (error) {
    showToast(error.message);
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "导出并生成摘要";
  }
});

async function summarizeFile() {
  if (!fileInput.files.length) {
    throw new Error("请先选择聊天记录文件");
  }
  return fetch("/api/summarize", {
    method: "POST",
    body: new FormData(form),
  });
}

async function summarizeWechat() {
  if (!wechatSessionSelect.value) {
    throw new Error("请先刷新并选择微信会话");
  }
  const payload = formFields();
  return fetch("/api/wechat/summarize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

copyButton.addEventListener("click", async () => {
  if (!latestReport) return;
  await navigator.clipboard.writeText(latestReport);
  showToast("已复制到剪贴板");
});

downloadButton.addEventListener("click", () => {
  if (!latestReport) return;
  const blob = new Blob([latestReport], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = latestDownloadName;
  link.click();
  URL.revokeObjectURL(url);
});

async function shutdownApp() {
  if (!window.confirm("关闭本地程序？")) return;
  shutdownButton.disabled = true;
  try {
    await fetch("/api/shutdown", { method: "POST" });
    document.body.innerHTML = '<main class="closed-state"><h1>程序已关闭</h1><p>可以关闭这个浏览器页面。</p></main>';
  } catch (error) {
    shutdownButton.disabled = false;
    showToast("关闭失败，请在任务管理器中结束程序");
  }
}

function syncDateBounds() {
  dateToInput.min = dateFromInput.value || "";
  dateFromInput.max = dateToInput.value || "";
}

function renderResult(data) {
  latestReport = data.report;
  latestDownloadName = data.download_name;

  if (data.engine === "deepseek") {
    const thinkingText = data.thinking === "enabled" ? `，思考：${data.reasoning_effort}` : "";
    previewTitle.textContent = `${data.model}${thinkingText}`;
  } else {
    previewTitle.textContent = "摘要已生成";
  }
  messageCount.textContent = data.message_count;
  speakerCount.textContent = data.speaker_count;
  encodingUsed.textContent = data.encoding;
  ignoredLines.textContent = data.ignored_lines;

  emptyState.hidden = true;
  copyButton.disabled = false;
  downloadButton.disabled = false;

  if (latestDownloadName.endsWith(".json")) {
    preview.hidden = true;
    rawOutput.hidden = false;
    rawOutput.value = latestReport;
  } else {
    rawOutput.hidden = true;
    preview.hidden = false;
    preview.innerHTML = renderMarkdown(latestReport);
  }
}

function updateEngineMode() {
  const isDeepSeek = engineSelect.value === "deepseek";
  deepseekFields.hidden = !isDeepSeek;
  formatSelect.disabled = isDeepSeek;
  if (isDeepSeek) {
    formatSelect.value = "markdown";
    privacyTitle.textContent = "DeepSeek API";
    privacyText.textContent = "筛选后的聊天内容会发送到 DeepSeek，API Key 只用于本次请求，不写入磁盘。";
  } else {
    privacyTitle.textContent = "本地处理";
    privacyText.textContent = "文件只会发送到本机服务，不会上传到外网。";
  }
}

function updateSourceMode() {
  const isWechat = sourceSelect.value === "wechat";
  fileSource.hidden = isWechat;
  wechatSource.hidden = !isWechat;
  if (isWechat) {
    privacyTitle.textContent = engineSelect.value === "deepseek" ? "微信 + DeepSeek" : "微信本地读取";
    privacyText.textContent =
      engineSelect.value === "deepseek"
        ? "先用 wechat-cli 本地导出，再把筛选后的内容发送到 DeepSeek。"
        : "使用 wechat-cli 只读本地微信数据，不上传到外网。";
  } else {
    updateEngineMode();
  }
}

async function checkWechatStatus() {
  wechatStatus.textContent = "检测中...";
  try {
    const response = await fetch("/api/wechat/status");
    const data = await response.json();
    if (!data.ok) throw new Error(data.error || "检测失败");
    wechatStatus.textContent = data.available
      ? `可用：${data.executable}`
      : `${data.message}；安装：${data.install_command}；初始化：${data.init_command}`;
  } catch (error) {
    wechatStatus.textContent = error.message;
  }
}

async function loadWechatSessions() {
  wechatStatus.textContent = "读取会话中...";
  wechatSessionsButton.disabled = true;
  try {
    const limit = encodeURIComponent(wechatSessionLimit.value || "50");
    const response = await fetch(`/api/wechat/sessions?limit=${limit}`);
    const data = await response.json();
    if (!data.ok) throw new Error(data.error || "读取会话失败");
    wechatSessionSelect.innerHTML = "";
    if (!data.sessions.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "未找到会话";
      wechatSessionSelect.appendChild(option);
    } else {
      for (const session of data.sessions) {
        const option = document.createElement("option");
        option.value = session.name;
        const label = session.display_name || session.name;
        option.textContent = Number.isInteger(session.message_count)
          ? `${label}（${session.message_count} 条）`
          : label;
        wechatSessionSelect.appendChild(option);
      }
    }
    wechatStatus.textContent = `已读取 ${data.sessions.length} 个会话`;
  } catch (error) {
    wechatStatus.textContent = error.message;
  } finally {
    wechatSessionsButton.disabled = false;
  }
}

function formFields() {
  const body = {};
  for (const [key, value] of new FormData(form).entries()) {
    if (value instanceof File) continue;
    body[key] = value;
  }
  return body;
}

function renderMarkdown(markdown) {
  const lines = markdown.split(/\r?\n/);
  const html = [];
  let inList = false;

  for (const line of lines) {
    if (line.startsWith("# ")) {
      if (inList) {
        html.push("</ul>");
        inList = false;
      }
      html.push(`<h1>${inline(line.slice(2))}</h1>`);
    } else if (line.startsWith("## ")) {
      if (inList) {
        html.push("</ul>");
        inList = false;
      }
      html.push(`<h2>${inline(line.slice(3))}</h2>`);
    } else if (line.startsWith("- ")) {
      if (!inList) {
        html.push("<ul>");
        inList = true;
      }
      html.push(`<li>${inline(line.slice(2))}</li>`);
    } else if (line.trim()) {
      if (inList) {
        html.push("</ul>");
        inList = false;
      }
      html.push(`<p>${inline(line)}</p>`);
    }
  }

  if (inList) {
    html.push("</ul>");
  }
  return html.join("");
}

function inline(text) {
  return escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function showToast(message) {
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 2600);
}
