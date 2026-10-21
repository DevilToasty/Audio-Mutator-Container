// Audio FX Mutator - UI
// Queries the sessions/tracks API in main.py:
//   GET  /api/effects               -- effect+knob schema
//   POST /api/sessions              -- create a session
//   GET  /api/sessions/{sid}        -- session + its tracks (restore)
//   POST /api/sessions/{sid}/tracks -- upload -> creates a track
//   PATCH /api/tracks/{tid}         -- save chain (marks dirty)
//   POST /api/tracks/{tid}/render   -- render from original, clears dirty
//   GET  /api/tracks/{tid}/audio    -- rendered if present, else original
//   GET/POST /api/presets           -- list / save chain presets
// The browser runs playback, playhead, and waveform

// One shared audio context using browser cloc
const audioContext = new (window.AudioContext || window.webkitAudioContext)();

// Effects from the server: { EffectName: { paramName: {min,max,default,step} } }
let EFFECTS = {};

// Current session id (created on load or restored from localStorage)
let sessionId = null;

// In-memory tracks
// Each has : { id, originalName, buffer, chain:[{effect_type,parameters}], isDirty, el, canvas, renderBtn, stripEl }
const tracks = [];

let startTime = 0; // audioContext time when playback began
let isPlaying = false;
let sources = []; // active AudioBufferSourceNodes

const fileInput = document.getElementById("fileInput");
const playBtn = document.getElementById("playBtn");
const stopBtn = document.getElementById("stopBtn");
const grid = document.getElementById("grid");

// Boot: loads effect schema, then restores or creates a session
init();

async function init() {
  EFFECTS = await (await fetch("/api/effects")).json();

  const saved = localStorage.getItem("afx_session_id");
  if (saved) {
    const res = await fetch("/api/sessions/" + saved);
    if (res.ok) {
      const session = await res.json();
      sessionId = session.id;
      for (const t of session.tracks) await restoreTrack(t);
    }
  }
  if (!sessionId) {
    const res = await fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "My Session" }),
    });
    sessionId = (await res.json()).id;
    localStorage.setItem("afx_session_id", sessionId);
  }
}

// Upload -> creates a track in the DB in the current session.
fileInput.addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`/api/sessions/${sessionId}/tracks`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    alert("Upload failed: " + (await res.text()));
    return;
  }
  const meta = await res.json();
  // meta: { id, original_name, chain:[], is_dirty:false, etc...}
  await addTrack(meta);
  fileInput.value = "";
});

// Build a track: fetch its audio, decode, draw, and build its plugin strip.
async function addTrack(meta) {
  const buffer = await loadBuffer(meta.id);
  const track = {
    id: meta.id,
    originalName: meta.original_name,
    buffer,
    chain: meta.chain || [],
    isDirty: !!meta.is_dirty,
  };
  mountTrack(track);
  tracks.push(track);
  playBtn.disabled = false;
  stopBtn.disabled = false;
}

// restore track returned by GET /api/sessions/{sid}
async function restoreTrack(t) {
  const buffer = await loadBuffer(t.id);
  const track = {
    id: t.id,
    originalName: t.name, // server stores display name in `name`
    buffer,
    chain: t.chain || [],
    isDirty: !!t.is_dirty,
  };
  mountTrack(track);
  tracks.push(track);
  playBtn.disabled = false;
  stopBtn.disabled = false;
}

// Fetch + decode a track's current audio (rendered if it exists, else original)
async function loadBuffer(trackId) {
  const res = await fetch(`/api/tracks/${trackId}/audio?t=` + Date.now());
  const arrayBuf = await res.arrayBuffer();
  return await audioContext.decodeAudioData(arrayBuf);
}

// Build one track's DOM: name, waveform canvas, and the plugin strip.
function mountTrack(track) {
  const el = document.createElement("div");
  el.className = "track";
  el.innerHTML = `
   <div class="track-head">
      <span class="name"></span>
      <button class="download-btn">Download</button>
      <button class="render-btn" disabled>Rendered</button>
    <canvas></canvas>
    <div class="strip"></div>
    <div class="strip-tools">
      <select class="add-fx">
        <option value="">+ Add effect...</option>
      </select>
      <button class="save-preset">Save as preset</button>
      <select class="apply-preset">
        <option value="">Apply preset...</option>
      </select>
    </div>`;
  grid.appendChild(el);

  track.el = el;
  track.canvas = el.querySelector("canvas");
  track.renderBtn = el.querySelector(".render-btn");
  // download btn
  el.querySelector(".download-btn").addEventListener("click", () => {
    window.location.href = `/api/tracks/${track.id}/download`;
  });
  track.stripEl = el.querySelector(".strip");
  el.querySelector(".name").textContent = track.originalName;

  // Populate "add effect" menu from the schema list
  const addFx = el.querySelector(".add-fx");
  for (const name of Object.keys(EFFECTS)) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    addFx.appendChild(opt);
  }
  addFx.addEventListener("change", () => {
    if (!addFx.value) return;
    addEffect(track, addFx.value);
    addFx.value = "";
  });

  // Render button: process on the server, then swap in new audio
  track.renderBtn.addEventListener("click", () => renderTrack(track));

  // Save-as-preset
  el.querySelector(".save-preset").addEventListener("click", () =>
    savePreset(track),
  );

  // Apply-preset menu, filled by refreshPresets()
  const applySel = el.querySelector(".apply-preset");
  applySel.addEventListener("change", () => {
    if (!applySel.value) return;
    applyPreset(track, applySel.value);
    applySel.value = "";
  });

  drawWaveform(track);
  renderStrip(track);
  refreshPresets(applySel);
}

// The plugin strip: one card per effect in the chain, a knob per param.
function renderStrip(track) {
  track.stripEl.innerHTML = "";
  track.chain.forEach((node, idx) => {
    const spec = EFFECTS[node.effect_type];
    if (!spec) return;

    const card = document.createElement("div");
    card.className = "fx-card";
    card.innerHTML = `
      <div class="fx-card-head">
        <span class="fx-name">${node.effect_type}</span>
        <button class="fx-remove" title="Remove">x</button>
      </div>
      <div class="knobs"></div>`;
    const knobs = card.querySelector(".knobs");

    for (const [pname, p] of Object.entries(spec)) {
      const val = node.parameters[pname] ?? p.default;
      const row = document.createElement("label");
      row.className = "knob";
      row.innerHTML = `
        <span class="knob-label">${pname}</span>
        <input type="range" min="${p.min}" max="${p.max}"
               step="${p.step}" value="${val}" />
        <span class="knob-val">${val}</span>`;
      const slider = row.querySelector("input");
      const out = row.querySelector(".knob-val");
      slider.addEventListener("input", () => {
        out.textContent = slider.value;
        node.parameters[pname] = parseFloat(slider.value);
        markDirty(track); // local flag + Render button lights
      });
      // Persist to the server when the user lets go of the knob.
      slider.addEventListener("change", () => saveChain(track));
      knobs.appendChild(row);
    }

    card.querySelector(".fx-remove").addEventListener("click", () => {
      track.chain.splice(idx, 1);
      markDirty(track);
      renderStrip(track);
      saveChain(track);
    });

    track.stripEl.appendChild(card);
  });
  updateRenderBtn(track);
}

// Add an effect with all params at defaults
function addEffect(track, name) {
  const spec = EFFECTS[name];
  const parameters = {};
  for (const [pname, p] of Object.entries(spec)) parameters[pname] = p.default;
  track.chain.push({ effect_type: name, parameters });
  markDirty(track);
  renderStrip(track);
  saveChain(track);
}

// Dirty flag: chain changed since last render -> Render button activates
function markDirty(track) {
  track.isDirty = true;
  updateRenderBtn(track);
}

function updateRenderBtn(track) {
  const b = track.renderBtn;
  if (track.isDirty) {
    b.disabled = false;
    b.textContent = "Render";
    b.classList.add("dirty");
  } else {
    b.textContent = track.chain.length ? "Rendered" : "No effects";
    b.disabled = true;
    b.classList.remove("dirty");
  }
}

// PATCH the chain to the server (marks is_dirty=1 server-side too)
async function saveChain(track) {
  await fetch(`/api/tracks/${track.id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chain: track.chain }),
  });
}

// Render: server processes original through the chain; swap in the audio.
async function renderTrack(track) {
  track.renderBtn.textContent = "Rendering...";
  track.renderBtn.disabled = true;
  const res = await fetch(`/api/tracks/${track.id}/render`, { method: "POST" });
  if (!res.ok) {
    alert("Render failed: " + (await res.text()));
    track.isDirty = true;
    updateRenderBtn(track);
    return;
  }
  track.buffer = await loadBuffer(track.id); // fetch the processed audio
  track.isDirty = false;
  updateRenderBtn(track);
  drawWaveform(track); // redraw with processed shape
}

// Presets: save this track's chain, list all, apply one to a track.
async function savePreset(track) {
  if (!track.chain.length) {
    alert("Add at least one effect first.");
    return;
  }
  const name = prompt("Preset name:");
  if (!name) return;
  const res = await fetch("/api/presets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, chain: track.chain }),
  });
  if (!res.ok) {
    alert("Save failed: " + (await res.text()));
    return;
  }
  // refresh every track's apply-preset menu so the new one appears
  document.querySelectorAll(".apply-preset").forEach(refreshPresets);
}

async function refreshPresets(selectEl) {
  const presets = await (await fetch("/api/presets")).json();
  // keep the first placeholder option - drop rest
  selectEl.length = 1;
  for (const p of presets) {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = p.name;
    opt.dataset.chain = JSON.stringify(p.chain);
    selectEl.appendChild(opt);
  }
}

function applyPreset(track, presetId) {
  const opt = track.el.querySelector(
    `.apply-preset option[value="${presetId}"]`,
  );
  if (!opt) return;
  // copy so editing the track never mutates the stored preset
  track.chain = JSON.parse(opt.dataset.chain);
  markDirty(track);
  renderStrip(track);
  saveChain(track);
}

// Waveform (left channel, one min/max bar per pixel column).
function drawWaveform(track) {
  const canvas = track.canvas;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(1, Math.floor(rect.width));
  canvas.height = Math.max(1, Math.floor(rect.height));
  const ctx = canvas.getContext("2d");
  const data = track.buffer.getChannelData(0);
  const w = canvas.width,
    h = canvas.height,
    mid = h / 2;
  const spp = Math.floor(data.length / w) || 1;

  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = "#4da3ff";
  ctx.beginPath();
  for (let x = 0; x < w; x++) {
    let min = 1.0,
      max = -1.0;
    for (let i = 0; i < spp; i++) {
      const s = data[x * spp + i] || 0;
      if (s < min) min = s;
      if (s > max) max = s;
    }
    ctx.moveTo(x, mid + min * mid);
    ctx.lineTo(x, mid + max * mid);
  }
  ctx.stroke();
}

// Transport: play all tracks aligned to one start time, shared playhead.
playBtn.addEventListener("click", async () => {
  if (isPlaying) return;
  await audioContext.resume();
  startTime = audioContext.currentTime;
  sources = tracks.map((t) => {
    const src = audioContext.createBufferSource();
    src.buffer = t.buffer;
    src.connect(audioContext.destination);
    src.start(startTime);
    return src;
  });
  isPlaying = true;
  requestAnimationFrame(drawPlayheads);
});

stopBtn.addEventListener("click", () => {
  sources.forEach((s) => {
    try {
      s.stop();
    } catch (e) {}
  });
  sources = [];
  isPlaying = false;
  tracks.forEach(drawWaveform);
});

function drawPlayheads() {
  if (!isPlaying) return;
  const elapsed = audioContext.currentTime - startTime;
  tracks.forEach((t) => {
    drawWaveform(t);
    const dur = t.buffer.duration;
    const x = (elapsed / dur) * t.canvas.width;
    if (x >= 0 && x <= t.canvas.width) {
      const ctx = t.canvas.getContext("2d");
      ctx.strokeStyle = "#ff5d5d";
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, t.canvas.height);
      ctx.stroke();
    }
  });
  requestAnimationFrame(drawPlayheads);
}
