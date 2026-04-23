// ---------- small helpers ----------
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function tpl(id) {
  return document.getElementById(id).content.firstElementChild.cloneNode(true);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

function formatDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}

// ---------- TTS ----------
const TTS = {
  voice: null,
  pickVoice() {
    const voices = speechSynthesis.getVoices();
    // Prefer an English voice
    this.voice = voices.find(v => /^en[-_]/i.test(v.lang)) || voices[0] || null;
  },
  speak(text) {
    if (!text.trim()) return;
    const u = new SpeechSynthesisUtterance(text);
    if (this.voice) u.voice = this.voice;
    u.lang = (this.voice && this.voice.lang) || "en-US";
    u.rate = 1.0;
    speechSynthesis.speak(u);
  },
  stop() { speechSynthesis.cancel(); },
};

if ("speechSynthesis" in window) {
  speechSynthesis.onvoiceschanged = () => TTS.pickVoice();
  TTS.pickVoice();
}

// Split streaming deltas into complete-sentence chunks for smoother TTS.
function makeTTSFeeder() {
  let buffer = "";
  return {
    push(delta) {
      buffer += delta;
      const parts = buffer.split(/([.!?]+[\s\n"')\]]+)/);
      // keep the trailing partial sentence in buffer
      let emit = "";
      let i = 0;
      for (; i + 1 < parts.length; i += 2) emit += parts[i] + parts[i + 1];
      buffer = parts.slice(i).join("");
      if (emit.trim()) TTS.speak(emit.trim());
    },
    flush() {
      if (buffer.trim()) TTS.speak(buffer.trim());
      buffer = "";
    },
  };
}

// ---------- STT ----------
const SpeechRecognitionCtor =
  window.SpeechRecognition || window.webkitSpeechRecognition;

class MicController {
  constructor(onInterim, onFinal, onEnd) {
    this.onInterim = onInterim;
    this.onFinal = onFinal;
    this.onEnd = onEnd;
    this.recognizer = null;
    this.listening = false;
  }

  supported() { return !!SpeechRecognitionCtor; }

  start() {
    if (!this.supported()) return false;
    const rec = new SpeechRecognitionCtor();
    rec.lang = "en-US";
    rec.continuous = true;
    rec.interimResults = true;
    let finalText = "";
    rec.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) finalText += r[0].transcript;
        else interim += r[0].transcript;
      }
      this.onInterim(finalText + interim);
    };
    rec.onerror = () => {};
    rec.onend = () => {
      this.listening = false;
      this.onFinal(finalText);
      this.onEnd();
    };
    this.recognizer = rec;
    this.listening = true;
    rec.start();
    return true;
  }

  stop() {
    if (this.recognizer && this.listening) this.recognizer.stop();
  }
}

// ---------- router ----------
const app = $("#app");
const nav = $("#nav");

let providers = [];

async function loadProviders() {
  const { providers: ps } = await api("/api/providers");
  providers = ps;
}

async function render(view) {
  app.innerHTML = "";
  nav.innerHTML = "";
  await view();
}

// ---------- home ----------
async function renderHome() {
  const node = tpl("tpl-home");
  app.appendChild(node);

  node.querySelector('[data-action="new"]').addEventListener("click", () => {
    render(renderNew);
  });

  const slot = node.querySelector('[data-slot="sessions"]');
  const { sessions } = await api("/api/sessions");
  if (!sessions.length) {
    slot.innerHTML = `<li style="justify-content:center;color:var(--muted)">세션이 없습니다. 새 세션을 만들어 시작하세요.</li>`;
    return;
  }
  for (const s of sessions) {
    const li = document.createElement("li");
    li.innerHTML = `
      <span class="title"></span>
      <span class="badge"></span>
      <span class="status"></span>
    `;
    li.querySelector(".title").textContent = s.title;
    li.querySelector(".badge").textContent = s.llm_provider;
    li.querySelector(".status").textContent =
      s.ended_at ? `종료 · ${formatDate(s.ended_at)}` : `진행중 · ${formatDate(s.created_at)}`;
    li.addEventListener("click", () => {
      if (s.ended_at) render(() => renderDetail(s.id));
      else render(() => renderChat(s.id));
    });
    slot.appendChild(li);
  }
}

// ---------- new session ----------
async function renderNew() {
  const node = tpl("tpl-new");
  app.appendChild(node);

  const form = node.querySelector('[data-slot="form"]');
  const providerSel = node.querySelector('[data-slot="provider"]');
  for (const p of providers) {
    const opt = document.createElement("option");
    opt.value = p.provider;
    opt.textContent = p.available ? `${p.label} · ${p.model}` : `${p.label} (API 키 미설정)`;
    if (!p.available) opt.disabled = true;
    providerSel.appendChild(opt);
  }
  const firstAvail = providers.find(p => p.available);
  if (firstAvail) providerSel.value = firstAvail.provider;

  const filesInput = form.elements["files"];
  const fileList = node.querySelector('[data-slot="files"]');
  const pickedFiles = [];
  const refreshFiles = () => {
    fileList.innerHTML = "";
    pickedFiles.forEach((f, i) => {
      const li = document.createElement("li");
      li.textContent = f.name;
      const rm = document.createElement("button");
      rm.type = "button";
      rm.textContent = "×";
      rm.addEventListener("click", () => {
        pickedFiles.splice(i, 1);
        refreshFiles();
      });
      li.appendChild(rm);
      fileList.appendChild(li);
    });
  };
  filesInput.addEventListener("change", () => {
    for (const f of filesInput.files) pickedFiles.push(f);
    filesInput.value = "";
    refreshFiles();
  });

  node.querySelector('[data-action="cancel"]').addEventListener("click", () => render(renderHome));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const payload = {
      title: fd.get("title").trim(),
      topic: fd.get("topic").trim(),
      situation: fd.get("situation").trim(),
      user_role: fd.get("user_role").trim(),
      model_role: fd.get("model_role").trim(),
      llm_provider: fd.get("llm_provider"),
    };
    try {
      const { session_id } = await api("/api/sessions", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (pickedFiles.length) {
        const upForm = new FormData();
        for (const f of pickedFiles) upForm.append("files", f);
        const up = await fetch(`/api/sessions/${session_id}/attachments`, {
          method: "POST",
          body: upForm,
        });
        if (!up.ok) throw new Error(`첨부 업로드 실패: ${up.status}`);
      }
      render(() => renderChat(session_id, { starting: true }));
    } catch (err) {
      alert("세션 생성 실패: " + err.message);
    }
  });
}

// ---------- chat ----------
async function streamSSE(url, body, { onDelta, onDone, onError }) {
  const res = await fetch(url, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    onError?.(new Error(`${res.status}: ${await res.text()}`));
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const events = buf.split("\n\n");
    buf = events.pop();
    for (const ev of events) {
      const line = ev.split("\n").find(l => l.startsWith("data: "));
      if (!line) continue;
      let obj;
      try { obj = JSON.parse(line.slice(6)); } catch { continue; }
      if (obj.error) { onError?.(new Error(obj.error)); continue; }
      if (obj.done) { onDone?.(obj.content); continue; }
      if (obj.delta) onDelta?.(obj.delta);
    }
  }
}

async function renderChat(sessionId, opts = {}) {
  const node = tpl("tpl-chat");
  app.appendChild(node);

  const chat = node.querySelector('[data-slot="chat"]');
  const titleEl = node.querySelector('[data-slot="title"]');
  const inputEl = node.querySelector('[data-slot="input"]');
  const micBtn = node.querySelector('[data-action="mic"]');
  const sendBtn = node.querySelector('[data-action="send"]');
  const endBtn = node.querySelector('[data-action="end"]');
  const hintEl = node.querySelector('[data-slot="hint"]');

  const { session, messages } = await api(`/api/sessions/${sessionId}`);
  titleEl.textContent = session.title;

  const bubbles = {};
  const addMessage = (role, content = "") => {
    const div = document.createElement("div");
    div.className = `msg ${role}`;
    div.textContent = content;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
  };
  for (const m of messages) addMessage(m.role, m.content);

  let lastSource = "text";
  let busy = false;

  const runAssistantStream = async (url, body) => {
    busy = true;
    sendBtn.disabled = true;
    const bubble = addMessage("assistant", "");
    const feeder = makeTTSFeeder();
    try {
      await streamSSE(url, body, {
        onDelta: (d) => {
          bubble.textContent += d;
          chat.scrollTop = chat.scrollHeight;
          feeder.push(d);
        },
        onDone: (full) => {
          if (full) bubble.textContent = full;
          feeder.flush();
        },
        onError: (err) => {
          bubble.textContent = `[오류] ${err.message}`;
          bubble.classList.add("error");
        },
      });
    } finally {
      busy = false;
      sendBtn.disabled = false;
    }
  };

  const mic = new MicController(
    (interim) => { inputEl.value = interim; lastSource = "voice"; },
    () => {},
    () => { micBtn.classList.remove("listening"); }
  );
  if (!mic.supported()) {
    micBtn.disabled = true;
    hintEl.textContent = "이 브라우저는 음성인식을 지원하지 않습니다. Chrome을 권장합니다.";
  }

  micBtn.addEventListener("click", () => {
    if (mic.listening) { mic.stop(); return; }
    if (!mic.start()) return;
    micBtn.classList.add("listening");
    TTS.stop();
  });

  const send = async () => {
    const content = inputEl.value.trim();
    if (!content || busy) return;
    inputEl.value = "";
    addMessage("user", content);
    const source = lastSource;
    lastSource = "text";
    await runAssistantStream(`/api/sessions/${sessionId}/messages`, { content, source });
  };
  sendBtn.addEventListener("click", send);
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });

  endBtn.addEventListener("click", async () => {
    if (busy) { alert("응답이 끝난 뒤 종료해 주세요."); return; }
    if (!confirm("세션을 종료하고 리포트를 받을까요?")) return;
    TTS.stop();
    endBtn.disabled = true;
    try {
      const { feedback } = await api(`/api/sessions/${sessionId}/end`, { method: "POST" });
      showFeedbackModal(feedback, () => render(renderHome));
    } catch (err) {
      alert("세션 종료 실패: " + err.message);
      endBtn.disabled = false;
    }
  });

  if (opts.starting) {
    await runAssistantStream(`/api/sessions/${sessionId}/start`, null);
  }
}

// ---------- feedback modal ----------
function renderScores(scores) {
  const rows = [
    ["질(Quality)", "quality"],
    ["유창성(Fluency)", "fluency"],
    ["의미전달(Communication)", "communication"],
    ["종합(Overall)", "overall"],
  ];
  return `<div class="scores">` + rows.map(([label, key]) => `
    <div class="score-row ${key === "overall" ? "overall" : ""}">
      <span>${label}</span>
      <div class="bar"><span style="width:${Math.max(0, Math.min(100, scores[key] ?? 0))}%"></span></div>
      <span class="value">${scores[key] ?? "-"}</span>
    </div>
  `).join("") + `</div>`;
}

function renderCorrections(corrections) {
  if (!corrections?.length) return "";
  return `<h4>표현 교정</h4>` + corrections.map(c => `
    <div class="correction">
      <div class="orig">${escapeHtml(c.original || "")}</div>
      <div class="sug">→ ${escapeHtml(c.suggestion || "")}</div>
      <div class="exp">${escapeHtml(c.explanation || "")}</div>
    </div>
  `).join("");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function renderFeedbackBody(feedback) {
  if (!feedback) return `<p class="error">피드백이 없습니다.</p>`;
  if (feedback.parse_error) {
    return `<p class="error">피드백 파싱 실패. 원문:</p><pre>${escapeHtml(feedback.raw_feedback || "")}</pre>`;
  }
  return `
    ${feedback.scores ? renderScores(feedback.scores) : ""}
    ${feedback.summary ? `<p class="summary">${escapeHtml(feedback.summary)}</p>` : ""}
    ${renderCorrections(feedback.corrections)}
  `;
}

function showFeedbackModal(feedback, onClose) {
  const node = tpl("tpl-feedback");
  node.querySelector('[data-slot="body"]').innerHTML = renderFeedbackBody(feedback);
  node.querySelector('[data-action="close"]').addEventListener("click", () => {
    node.remove();
    onClose?.();
  });
  document.body.appendChild(node);
}

// ---------- detail view ----------
async function renderDetail(sessionId) {
  const node = tpl("tpl-detail");
  app.appendChild(node);
  const { session, messages, attachments } = await api(`/api/sessions/${sessionId}`);
  node.querySelector('[data-slot="title"]').textContent = session.title;
  node.querySelector('[data-action="back"]').addEventListener("click", () => render(renderHome));

  const meta = node.querySelector('[data-slot="meta"]');
  meta.innerHTML = `
    <strong>주제</strong><span>${escapeHtml(session.topic)}</span>
    <strong>상황</strong><span>${escapeHtml(session.situation)}</span>
    <strong>내 역할</strong><span>${escapeHtml(session.user_role)}</span>
    <strong>모델 역할</strong><span>${escapeHtml(session.model_role)}</span>
    <strong>LLM</strong><span>${escapeHtml(session.llm_provider)} · ${escapeHtml(session.llm_model)}</span>
    <strong>생성</strong><span>${formatDate(session.created_at)}</span>
    <strong>종료</strong><span>${formatDate(session.ended_at)}</span>
    <strong>첨부</strong><span>${attachments.map(a => escapeHtml(a.filename)).join(", ") || "-"}</span>
  `;

  const chat = node.querySelector('[data-slot="chat"]');
  for (const m of messages) {
    const div = document.createElement("div");
    div.className = `msg ${m.role}`;
    div.textContent = m.content;
    chat.appendChild(div);
  }

  const fbSlot = node.querySelector('[data-slot="feedback"]');
  if (session.feedback) {
    fbSlot.innerHTML = `<h3>리포트</h3>` + renderFeedbackBody(session.feedback);
  }
}

// ---------- bootstrap ----------
(async () => {
  try {
    await loadProviders();
  } catch (err) {
    app.innerHTML = `<p class="error">초기화 실패: ${err.message}</p>`;
    return;
  }
  render(renderHome);
})();
