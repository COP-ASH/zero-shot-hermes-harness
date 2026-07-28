/* ================================================================
   UP Police Data Analyst — JavaScript Application
   ================================================================ */

"use strict";

// ── State ──────────────────────────────────────────────────────────
let sessionId = null;
let isQuerying = false;
let lastRunId = null;
let uploadedFiles = []; // [{name, view_name, columns, row_count}]
let chatHistory = [];

// ── Init ───────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  checkHealth();
  createSession();
});

async function checkHealth() {
  try {
    const r = await fetch("/health");
    const data = await r.json();
    const info = data.data || data;
    const label = document.getElementById("provider-label");
    if (info.key_configured) {
      label.textContent = `${info.provider} / ${(info.model || "").split("/").pop()}`;
    } else {
      label.textContent = "No API key configured";
      document.querySelector(".pulse-dot").style.background = "var(--danger)";
    }
  } catch {
    document.getElementById("provider-label").textContent = "Offline";
    document.querySelector(".pulse-dot").style.background = "var(--danger)";
  }
}

async function createSession() {
  try {
    const r = await fetch("/api/sessions", { method: "POST" });
    const data = await r.json();
    sessionId = data.data?.session_id || data.session_id;
    const el = document.getElementById("session-id-display");
    if (el) el.textContent = sessionId?.slice(0, 12) + "…";
    document.getElementById("session-info").style.display = "block";
  } catch (e) {
    console.error("Failed to create session:", e);
  }
}

// ── File Upload ────────────────────────────────────────────────────
function handleDrop(e) {
  e.preventDefault();
  document.getElementById("upload-zone").classList.remove("drag-over");
  const files = [...e.dataTransfer.files].filter(f => f.name.endsWith(".csv"));
  if (files.length === 0) {
    showError("Please drop CSV files only.");
    return;
  }
  uploadFiles(files);
}

function handleFileSelect(e) {
  const files = [...e.target.files];
  if (files.length === 0) return;
  uploadFiles(files);
  e.target.value = "";
}

function addMoreFiles() {
  document.getElementById("file-input").click();
}

function switchSource(source) {
  if (source === "mssql") {
    showStubToast("MSSQL integration is coming in Phase 2!");
    return;
  }
}

async function uploadFiles(files) {
  if (!sessionId) {
    await createSession();
  }

  const formData = new FormData();
  files.forEach(f => formData.append("files", f));

  // Show loading state
  const zone = document.getElementById("upload-zone");
  zone.innerHTML = `<div class="upload-progress"><div class="upload-spinner"></div> Uploading ${files.length} file(s)…</div>`;

  try {
    const r = await fetch(`/api/sessions/${sessionId}/upload`, {
      method: "POST",
      body: formData,
    });
    const data = await r.json();
    if (!r.ok) {
      throw new Error(data.detail || data.error || "Upload failed");
    }

    const allFiles = data.data?.files || data.files || [];
    uploadedFiles = allFiles;

    renderFilesList(allFiles);
    renderSchema(allFiles);
    enableChat();
    resetUploadZone();

  } catch (err) {
    resetUploadZone();
    showError(`Upload failed: ${err.message}`);
  }
}

function resetUploadZone() {
  document.getElementById("upload-zone").innerHTML = `
    <div class="upload-icon">📁</div>
    <div class="upload-text">Drag &amp; drop CSVs here</div>
    <div class="upload-hint">or click to browse</div>
    <input type="file" id="file-input" multiple accept=".csv" style="display:none" onchange="handleFileSelect(event)" />
    <button class="upload-btn" onclick="document.getElementById('file-input').click()">Choose Files</button>
  `;
}

function renderFilesList(files) {
  const section = document.getElementById("files-section");
  const list = document.getElementById("files-list");
  section.style.display = "block";

  list.innerHTML = files.map(f => `
    <li class="file-item">
      <span class="file-icon">📄</span>
      <span class="file-name" title="${f.name}">${f.name}</span>
      <span class="file-rows">${formatNum(f.row_count)} rows</span>
    </li>
  `).join("");
}

function renderSchema(files) {
  const section = document.getElementById("schema-section");
  const container = document.getElementById("schema-list");
  section.style.display = "block";

  container.innerHTML = files.map(f => `
    <div class="schema-table">
      <div class="schema-table-header">
        🗂️ <span style="font-family:var(--mono)">${f.view_name}</span>
        <span style="color:var(--text-muted);font-size:10px;margin-left:auto">${formatNum(f.row_count)} rows</span>
      </div>
      <div class="schema-table-cols">
        ${(f.columns || []).map(c => `
          <div class="schema-col">
            <span class="col-name">${c.name}</span>
            <span class="col-type">${c.dtype}</span>
          </div>
        `).join("")}
      </div>
    </div>
  `).join("");
}

function enableChat() {
  const input = document.getElementById("question-input");
  const btn = document.getElementById("send-btn");
  const hint = document.getElementById("input-hint");
  input.disabled = false;
  btn.disabled = false;
  hint.textContent = "Shift+Enter for newline • Enter to send";

  document.getElementById("welcome-screen").style.display = "none";
  document.getElementById("chat-container").style.display = "flex";

  const fileNames = uploadedFiles.map(f => f.name).join(", ");
  document.getElementById("topbar-title").textContent = `Analysing: ${fileNames}`;

  input.focus();
}

// ── Chat ───────────────────────────────────────────────────────────
function handleKeydown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendQuestion();
  }
}

function autoResize(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 160) + "px";
}

function setExample(text) {
  const input = document.getElementById("question-input");
  input.value = text;
  if (!input.disabled) {
    sendQuestion();
  }
}

async function sendQuestion() {
  const input = document.getElementById("question-input");
  const question = input.value.trim();
  if (!question || isQuerying) return;

  input.value = "";
  input.style.height = "auto";
  isQuerying = true;
  setInputDisabled(true);

  // Add user bubble
  appendUserMessage(question);

  // Show typing indicator
  const typingId = appendTypingIndicator();

  // Show step overlay
  showStepOverlay();
  setStep("plan", "running");

  try {
    // Simulate step progression for UX (real steps happen server-side)
    const stepTimer1 = setTimeout(() => setStep("execute", "running"), 800);
    const stepTimer2 = setTimeout(() => setStep("reflect", "running"), 1600);
    const stepTimer3 = setTimeout(() => setStep("synthesize", "running"), 2400);

    const r = await fetch(`/api/sessions/${sessionId}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });

    clearTimeout(stepTimer1);
    clearTimeout(stepTimer2);
    clearTimeout(stepTimer3);

    const data = await r.json();
    const result = data.data || data;

    hideStepOverlay();
    removeTypingIndicator(typingId);

    if (!r.ok || result.status === "failed") {
      appendErrorMessage(result.error || result.answer || "An error occurred.");
    } else {
      lastRunId = result.run_id;
      appendAssistantMessage(result);
      // Update local chat history
      chatHistory.push({ role: "user", content: question });
      chatHistory.push({ role: "assistant", content: result.answer || "" });
    }

  } catch (err) {
    hideStepOverlay();
    removeTypingIndicator(typingId);
    appendErrorMessage(`Network error: ${err.message}`);
  } finally {
    isQuerying = false;
    setInputDisabled(false);
    document.getElementById("question-input").focus();
  }
}

function setInputDisabled(disabled) {
  document.getElementById("question-input").disabled = disabled;
  document.getElementById("send-btn").disabled = disabled;
}

// ── Message Rendering ──────────────────────────────────────────────
function appendUserMessage(text) {
  const msgs = document.getElementById("messages");
  const div = document.createElement("div");
  div.className = "msg user";
  div.innerHTML = `
    <div class="msg-bubble">${escapeHtml(text)}</div>
    <div class="msg-meta">${timeStr()}</div>
  `;
  msgs.appendChild(div);
  scrollToBottom();
}

function appendTypingIndicator() {
  const msgs = document.getElementById("messages");
  const id = "typing-" + Date.now();
  const div = document.createElement("div");
  div.className = "msg assistant";
  div.id = id;
  div.innerHTML = `
    <div class="msg-bubble">
      <div class="typing-dots"><span></span><span></span><span></span></div>
    </div>
  `;
  msgs.appendChild(div);
  scrollToBottom();
  return id;
}

function removeTypingIndicator(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function appendAssistantMessage(result) {
  const msgs = document.getElementById("messages");
  const div = document.createElement("div");
  div.className = "msg assistant";

  const chartId = "chart-" + Date.now();
  const codeId = "code-" + Date.now();

  let chartHtml = "";
  if (result.chart) {
    chartHtml = `<div class="answer-chart" id="${chartId}"></div>`;
  }

  let codeHtml = "";
  if (result.sql) {
    codeHtml = `
      <div class="code-block-wrapper">
        <button class="code-toggle" onclick="toggleCode('${codeId}')">
          <span>💻</span> View SQL query
          <span id="${codeId}-arrow" style="margin-left:auto">▼</span>
        </button>
        <pre class="code-block" id="${codeId}">${escapeHtml(result.sql)}</pre>
      </div>
    `;
  }

  let qualityHtml = "";
  if (result.data_quality_notes) {
    qualityHtml = `
      <div class="quality-note">
        ⚠️ <span>${escapeHtml(result.data_quality_notes)}</span>
      </div>
    `;
  }

  let followUpsHtml = "";
  if (result.follow_ups && result.follow_ups.length > 0) {
    const chips = result.follow_ups.map(q =>
      `<button class="follow-up-chip" onclick="setExampleAndSend(${JSON.stringify(q)})">${escapeHtml(q)}</button>`
    ).join("");
    followUpsHtml = `
      <div class="follow-ups">
        <div class="follow-up-label">Suggested follow-ups</div>
        <div class="follow-up-chips">${chips}</div>
      </div>
    `;
  }

  const downloadHtml = lastRunId ? `
    <div class="action-bar">
      <a class="btn-action" href="/api/sessions/${sessionId}/download/${result.run_id}" download>
        ⬇️ Download CSV
      </a>
      <button class="btn-action stub" onclick="showStubToast('PDF reports coming in Phase 2!')">
        📄 Generate PDF <span class="stub-badge">Phase 2</span>
      </button>
    </div>
  ` : "";

  div.innerHTML = `
    <div class="msg-bubble">
      <div class="answer-card">
        <div class="answer-text">${escapeHtml(result.answer || "Analysis complete.")}</div>
        ${chartHtml}
        ${codeHtml}
        ${qualityHtml}
        ${followUpsHtml}
        ${downloadHtml}
      </div>
    </div>
    <div class="msg-meta">${timeStr()} · ${result.model ? result.model.split("/").pop() : "AI"}</div>
  `;

  msgs.appendChild(div);

  // Render Plotly chart after DOM insertion
  if (result.chart) {
    renderChart(chartId, result.chart);
  }

  scrollToBottom();
}

function appendErrorMessage(text) {
  const msgs = document.getElementById("messages");
  const div = document.createElement("div");
  div.className = "msg assistant";
  div.innerHTML = `
    <div class="msg-bubble msg-error">
      <div>⚠️ ${escapeHtml(text)}</div>
    </div>
  `;
  msgs.appendChild(div);
  scrollToBottom();
}

function toggleCode(id) {
  const el = document.getElementById(id);
  const arrow = document.getElementById(id + "-arrow");
  el.classList.toggle("open");
  if (arrow) arrow.textContent = el.classList.contains("open") ? "▲" : "▼";
}

function setExampleAndSend(text) {
  const input = document.getElementById("question-input");
  input.value = text;
  sendQuestion();
}

// ── Chart Rendering ────────────────────────────────────────────────
function renderChart(containerId, chartSpec) {
  const el = document.getElementById(containerId);
  if (!el) return;

  const layout = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Inter, sans-serif", color: "#94a3b8", size: 12 },
    title: {
      text: chartSpec.title || "",
      font: { color: "#f1f5f9", size: 14 },
      x: 0.05,
    },
    xaxis: {
      gridcolor: "rgba(99,149,255,0.1)",
      zerolinecolor: "rgba(99,149,255,0.2)",
      color: "#94a3b8",
    },
    yaxis: {
      gridcolor: "rgba(99,149,255,0.1)",
      zerolinecolor: "rgba(99,149,255,0.2)",
      color: "#94a3b8",
    },
    margin: { t: 50, r: 20, b: 60, l: 60 },
    legend: { bgcolor: "rgba(0,0,0,0)", font: { color: "#94a3b8" } },
  };

  let trace = {};
  const type = (chartSpec.type || "bar").toLowerCase();

  if (type === "bar") {
    trace = {
      type: "bar",
      x: chartSpec.x_data || [],
      y: chartSpec.y_data || [],
      name: chartSpec.y || "",
      marker: {
        color: "rgba(59,130,246,0.8)",
        line: { color: "rgba(59,130,246,1)", width: 1 },
      },
    };
    if (chartSpec.orientation === "h") {
      trace.orientation = "h";
      [trace.x, trace.y] = [trace.y, trace.x];
    }
  } else if (type === "line") {
    trace = {
      type: "scatter",
      mode: "lines+markers",
      x: chartSpec.x_data || [],
      y: chartSpec.y_data || [],
      line: { color: "#3b82f6", width: 2 },
      marker: { color: "#60a5fa", size: 6 },
    };
  } else if (type === "pie") {
    trace = {
      type: "pie",
      labels: chartSpec.x_data || [],
      values: chartSpec.y_data || [],
      hole: 0.35,
      marker: {
        colors: ["#3b82f6","#6366f1","#8b5cf6","#ec4899","#f59e0b","#10b981","#06b6d4","#f43f5e"],
      },
      textinfo: "percent+label",
      textfont: { color: "#f1f5f9" },
    };
  } else {
    // Default bar
    trace = { type: "bar", x: chartSpec.x_data || [], y: chartSpec.y_data || [] };
  }

  Plotly.newPlot(el, [trace], layout, {
    displayModeBar: true,
    modeBarButtonsToRemove: ["pan2d", "select2d", "lasso2d", "toImage"],
    displaylogo: false,
    responsive: true,
  });
}

// ── Step Overlay ───────────────────────────────────────────────────
function showStepOverlay() {
  const steps = ["plan", "execute", "reflect", "synthesize"];
  steps.forEach(s => {
    setStepState(s, "waiting");
  });
  document.getElementById("step-overlay").style.display = "flex";
}

function hideStepOverlay() {
  document.getElementById("step-overlay").style.display = "none";
}

function setStep(name, status) {
  setStepState(name, status);
  if (status === "running") {
    // Mark all previous steps as done
    const order = ["plan", "execute", "reflect", "synthesize"];
    const idx = order.indexOf(name);
    for (let i = 0; i < idx; i++) {
      setStepState(order[i], "done");
    }
  }
}

function setStepState(name, state) {
  const el = document.getElementById(`step-${name}`);
  const statusEl = document.getElementById(`step-${name}-status`);
  if (!el || !statusEl) return;
  el.className = "step " + (state === "waiting" ? "" : state);
  statusEl.textContent = state === "done" ? "✓ done" : state === "running" ? "running…" : "waiting";
}

// ── New Session ────────────────────────────────────────────────────
async function newSession() {
  if (isQuerying) return;
  if (!confirm("Start a new session? Your current uploads will be cleared.")) return;

  uploadedFiles = [];
  chatHistory = [];
  lastRunId = null;

  document.getElementById("files-section").style.display = "none";
  document.getElementById("schema-section").style.display = "none";
  document.getElementById("messages").innerHTML = "";
  document.getElementById("chat-container").style.display = "none";
  document.getElementById("welcome-screen").style.display = "flex";
  document.getElementById("topbar-title").textContent = "Upload data to begin analysis";
  document.getElementById("question-input").disabled = true;
  document.getElementById("send-btn").disabled = true;
  document.getElementById("input-hint").textContent = "Upload a CSV to start asking questions";

  await createSession();
}

// ── Utilities ──────────────────────────────────────────────────────
function scrollToBottom() {
  const container = document.getElementById("chat-container");
  if (container) container.scrollTop = container.scrollHeight;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatNum(n) {
  if (!n && n !== 0) return "?";
  return Number(n).toLocaleString();
}

function timeStr() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function showError(msg) {
  const msgs = document.getElementById("messages");
  if (!msgs) { alert(msg); return; }
  appendErrorMessage(msg);
}

function showStubToast(msg) {
  // Simple toast notification for stub features
  const toast = document.createElement("div");
  toast.style.cssText = `
    position:fixed; bottom:100px; left:50%; transform:translateX(-50%);
    background:var(--bg-elevated); border:1px solid var(--police-gold);
    color:var(--police-gold); padding:10px 20px; border-radius:100px;
    font-size:13px; z-index:999; animation:fadeIn 0.2s ease;
    box-shadow:0 4px 20px rgba(0,0,0,0.4);
  `;
  toast.textContent = "🚧 " + msg;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}
