// JUJU PWA client.
//
// Talks to the backend over a WebSocket for voice + chat, and over REST for
// memory inspection. Uses MediaRecorder for mic capture and the Web Audio API
// to play back the mp3 the server sends.

const $ = (sel) => document.querySelector(sel);

const state = {
  token: localStorage.getItem("juju.token"),
  username: localStorage.getItem("juju.user"),
  ws: null,
  recording: false,
  recorder: null,
  chunks: [],
  audioCtx: null,
};

// ---------- registration of service worker
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/service-worker.js").catch(() => {});
}

// ---------- UI helpers
function setStatus(text, online = false) {
  const el = $("#status");
  el.textContent = text;
  el.classList.toggle("online", online);
}

function appendMessage(role, text, meta = "") {
  const div = document.createElement("div");
  div.className = `msg ${role === "user" ? "user" : "bot"}`;
  div.textContent = text;
  if (meta) {
    const m = document.createElement("div");
    m.className = "meta";
    m.textContent = meta;
    div.appendChild(m);
  }
  $("#messages").appendChild(div);
  $("#messages").scrollTop = $("#messages").scrollHeight;
}

// ---------- auth
async function login(username) {
  const r = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username }),
  });
  if (!r.ok) throw new Error("login failed");
  const data = await r.json();
  state.token = data.token;
  state.username = data.user;
  localStorage.setItem("juju.token", state.token);
  localStorage.setItem("juju.user", state.username);
}

async function fetchDeviceInfo() {
  const r = await fetch("/api/tools", {
    headers: { authorization: `Bearer ${state.token}` },
  });
  if (!r.ok) return;
  const data = await r.json();
  $("#device-info-body").textContent = JSON.stringify(data, null, 2);
}

// ---------- websocket
function openSocket() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/api/ws/voice`);
  state.ws = ws;

  ws.onopen = () => {
    ws.send(JSON.stringify({ type: "auth", token: state.token }));
  };
  ws.onmessage = (ev) => handleEvent(JSON.parse(ev.data));
  ws.onclose = () => {
    setStatus("offline");
    setTimeout(openSocket, 1500);
  };
}

function handleEvent(msg) {
  switch (msg.type) {
    case "ready":
      setStatus(`online — ${msg.user}`, true);
      fetchDeviceInfo();
      break;
    case "transcript":
      appendMessage("user", msg.text);
      break;
    case "reply":
      appendMessage(
        "bot",
        msg.text,
        `${msg.provider} · ${msg.model}${msg.used_agents ? " · agents" : ""}`
      );
      break;
    case "audio":
      playAudio(msg.data_b64);
      break;
    case "permission_request":
      askPermission(msg);
      break;
    case "error":
      appendMessage("bot", `[error] ${msg.error}`);
      break;
  }
}

function playAudio(b64) {
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const blob = new Blob([bytes], { type: "audio/mpeg" });
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  audio.play().catch(() => {});
}

// ---------- permissions
function askPermission(req) {
  const dlg = $("#perm-dialog");
  $("#perm-title").textContent = `Permission: ${req.scope}`;
  $("#perm-body").textContent = req.resource
    ? `JUJU is asking to access:\n${req.resource}`
    : "JUJU is asking for a new capability.";
  dlg.returnValue = "deny";
  dlg.showModal();
  dlg.addEventListener(
    "close",
    () => {
      state.ws?.send(
        JSON.stringify({
          type: "permission_response",
          request_id: req.id,
          decision: dlg.returnValue,
          scope: req.scope,
          resource: req.resource,
        })
      );
    },
    { once: true }
  );
}

// ---------- mic capture
async function startRecording() {
  if (state.recording) return;
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
  state.recorder = recorder;
  state.chunks = [];
  recorder.ondataavailable = (e) => e.data.size && state.chunks.push(e.data);
  recorder.onstop = async () => {
    const blob = new Blob(state.chunks, { type: "audio/webm" });
    const buf = await blob.arrayBuffer();
    const b64 = btoa(String.fromCharCode(...new Uint8Array(buf)));
    state.ws?.send(
      JSON.stringify({ type: "audio", mime: "audio/webm", data_b64: b64 })
    );
    stream.getTracks().forEach((t) => t.stop());
  };
  recorder.start();
  state.recording = true;
  $("#mic-btn").classList.add("recording");
  setupMeter(stream);
}

function stopRecording() {
  if (!state.recording) return;
  state.recorder?.stop();
  state.recording = false;
  $("#mic-btn").classList.remove("recording");
}

function setupMeter(stream) {
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const src = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 256;
  src.connect(analyser);
  const data = new Uint8Array(analyser.frequencyBinCount);
  const bar = $("#meter > div");
  function tick() {
    if (!state.recording) {
      bar.style.width = "0%";
      return;
    }
    analyser.getByteFrequencyData(data);
    const avg = data.reduce((a, b) => a + b, 0) / data.length;
    bar.style.width = `${Math.min(100, (avg / 128) * 100)}%`;
    requestAnimationFrame(tick);
  }
  tick();
}

// ---------- text input
$("#text-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = $("#text-input");
  const text = input.value.trim();
  if (!text) return;
  appendMessage("user", text);
  state.ws?.send(JSON.stringify({ type: "text", text }));
  input.value = "";
});

// ---------- mic button (hold-to-talk)
const mic = $("#mic-btn");
["mousedown", "touchstart"].forEach((ev) =>
  mic.addEventListener(ev, (e) => {
    e.preventDefault();
    startRecording();
  })
);
["mouseup", "mouseleave", "touchend", "touchcancel"].forEach((ev) =>
  mic.addEventListener(ev, (e) => {
    e.preventDefault();
    stopRecording();
  })
);

// ---------- login
$("#login-btn").addEventListener("click", async () => {
  const name = $("#username").value.trim();
  if (!name) return;
  await login(name);
  $("#login-panel").hidden = true;
  $("#chat-panel").hidden = false;
  openSocket();
});

// auto-resume
if (state.token && state.username) {
  $("#username").value = state.username;
  $("#login-panel").hidden = true;
  $("#chat-panel").hidden = false;
  openSocket();
}
