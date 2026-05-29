// ===== VEGA UI =====

const $ = (id) => document.getElementById(id);

// ===== Auth: bearer token auto-attached to all fetch + WS =====
let VEGA_TOKEN = localStorage.getItem("vega_token") || "";

(function _wrapFetch() {
  const _origFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    init = init || {};
    init.headers = new Headers(init.headers || {});
    if (VEGA_TOKEN && !init.headers.has("Authorization")) {
      init.headers.set("Authorization", "Bearer " + VEGA_TOKEN);
    }
    return _origFetch(input, init).then((r) => {
      if (r.status === 401 && !init._retried) {
        // Token invalid / missing — prompt PIN flow
        _promptLogin();
      }
      return r;
    });
  };
})();

async function _promptLogin() {
  if (window._vega_login_active) return;
  window._vega_login_active = true;
  try {
    const info = await (await fetch("/api/auth/info")).json();
    let pin = "";
    if (info.pin_required) {
      pin = prompt("PIN richiesto per accesso a Vega:");
      if (!pin) { window._vega_login_active = false; return; }
    }
    const r = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin }),
    });
    const j = await r.json();
    if (j.ok && j.token) {
      VEGA_TOKEN = j.token;
      localStorage.setItem("vega_token", j.token);
      location.reload();
    } else {
      alert("Login fallito: " + (j.error || "?"));
    }
  } catch (e) {
    console.error("login error", e);
  } finally {
    window._vega_login_active = false;
  }
}

// Initial silent token bootstrap (localhost gets it automatically)
(async function _bootstrapAuth() {
  if (VEGA_TOKEN) return;
  try {
    const r = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const j = await r.json();
    if (j.ok && j.token) {
      VEGA_TOKEN = j.token;
      localStorage.setItem("vega_token", j.token);
    }
  } catch (e) {}
})();

// Register service worker for PWA install support
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

// Mobile detection
const IS_MOBILE = /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent) || window.innerWidth < 800;
if (IS_MOBILE) document.body.classList.add("mobile");

// ----- Dynamic theme by hour -----
function applyDynamicTheme() {
  const h = new Date().getHours();
  let primary, soft, label;
  if (h >= 5 && h < 9) {
    // Alba: arancio caldo
    primary = "#ffb060"; soft = "rgba(255,176,96,0.18)"; label = "alba";
  } else if (h >= 9 && h < 17) {
    // Giorno: periwinkle VEGA (stella blu-bianca, non piu' ciano)
    primary = "#8ba4ff"; soft = "rgba(139,164,255,0.18)"; label = "giorno";
  } else if (h >= 17 && h < 20) {
    // Sera: magenta/viola
    primary = "#c47dff"; soft = "rgba(196,125,255,0.18)"; label = "sera";
  } else {
    // Notte: blu profondo
    primary = "#5990ff"; soft = "rgba(89,144,255,0.18)"; label = "notte";
  }
  const root = document.documentElement;
  root.style.setProperty("--cyan", primary);
  root.style.setProperty("--cyan-soft", soft);
  // Update glow for the new color
  const glowRgb = primary.match(/[0-9a-f]{2}/gi).map(x => parseInt(x, 16)).join(",");
  root.style.setProperty("--cyan-glow", `rgba(${glowRgb}, 0.65)`);
  root.style.setProperty("--cyan-dim", `rgba(${glowRgb}, 0.08)`);
  // also update state color map
  stateColors.idle = primary;
  stateColors.boot = primary;
}
setInterval(applyDynamicTheme, 600000);  // re-check every 10 min
window.addEventListener("DOMContentLoaded", applyDynamicTheme);

// ----- Canvas viz -----
const canvas = $("viz");
// Liquid/Generative orb: WebGL fragment shader with graceful 2D fallback.
let gl = null, ctx = null;
try {
  gl = canvas.getContext("webgl", { alpha: true, premultipliedAlpha: false, antialias: true })
    || canvas.getContext("experimental-webgl", { alpha: true, premultipliedAlpha: false });
} catch (e) { gl = null; }
if (!gl) { ctx = canvas.getContext("2d"); }
let DPR = window.devicePixelRatio || 1;

// Voice waveform (horizontal under HUD)
const waveformCanvas = document.getElementById("waveform");
const waveformCtx = waveformCanvas ? waveformCanvas.getContext("2d") : null;
const waveformHistory = new Array(96).fill(0);
function resizeWaveform() {
  if (!waveformCanvas) return;
  const dpr = window.devicePixelRatio || 1;
  const rect = waveformCanvas.getBoundingClientRect();
  waveformCanvas.width = rect.width * dpr;
  waveformCanvas.height = rect.height * dpr;
}
window.addEventListener("resize", resizeWaveform);
function drawWaveform() {
  if (!waveformCtx) return;
  const w = waveformCanvas.width;
  const h = waveformCanvas.height;
  waveformCtx.clearRect(0, 0, w, h);
  // Shift history left, append latest level
  waveformHistory.shift();
  waveformHistory.push(targetLevel);

  const color = stateColors[currentState] || "#8ba4ff";
  const bars = waveformHistory.length;
  const barW = w / bars;
  const cy = h / 2;
  waveformCtx.fillStyle = color;
  waveformCtx.shadowColor = color;
  waveformCtx.shadowBlur = 6;
  for (let i = 0; i < bars; i++) {
    const v = waveformHistory[i];
    const barH = Math.max(2, v * h * 1.4);
    const opa = 0.4 + Math.min(0.6, v * 1.2);
    waveformCtx.globalAlpha = opa;
    waveformCtx.fillRect(i * barW + barW * 0.15, cy - barH / 2, barW * 0.7, barH);
  }
  waveformCtx.globalAlpha = 1;
  waveformCtx.shadowBlur = 0;
  requestAnimationFrame(drawWaveform);
}

function resize() {
  DPR = Math.min(window.devicePixelRatio || 1, 2);
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(1, rect.width * DPR);
  canvas.height = Math.max(1, rect.height * DPR);
  if (gl) gl.viewport(0, 0, canvas.width, canvas.height);
}
window.addEventListener("resize", resize);

let currentLevel = 0;
let targetLevel = 0;
let currentState = "boot";
let frame = 0;

const stateColors = {
  boot: "#8ba4ff",
  loading: "#ffc940",
  idle: "#8ba4ff",
  listening: "#ffc940",
  thinking: "#c77dff",
  speaking: "#34ffb9",
};

const STATE_LABEL = {
  boot: "AVVIO",
  loading: "CARICAMENTO",
  idle: "IN ASCOLTO",
  listening: "TI ASCOLTO",
  thinking: "ELABORO",
  speaking: "PARLO",
};

// particles
const particles = [];
function emitParticles(intensity) {
  const n = Math.min(5, Math.floor(intensity * 8));
  const rect = canvas.getBoundingClientRect();
  const cx = rect.width / 2;
  const cy = rect.height / 2;
  for (let i = 0; i < n; i++) {
    const a = Math.random() * Math.PI * 2;
    const speed = 0.6 + Math.random() * 1.2 + intensity * 1.2;
    particles.push({
      x: cx, y: cy,
      vx: Math.cos(a) * speed, vy: Math.sin(a) * speed,
      life: 1, decay: 0.012 + Math.random() * 0.012,
      size: 1 + Math.random() * 2,
    });
  }
}

function drawParticles(color) {
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i];
    p.x += p.vx; p.y += p.vy; p.life -= p.decay;
    if (p.life <= 0) { particles.splice(i, 1); continue; }
    ctx.beginPath();
    ctx.arc(p.x * DPR, p.y * DPR, p.size * DPR, 0, Math.PI * 2);
    ctx.fillStyle = color + Math.floor(p.life * 255).toString(16).padStart(2, "0");
    ctx.fill();
  }
}

function draw2D() {
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  // Smoothing: faster response, more decay when level drops to 0
  if (targetLevel > currentLevel) {
    currentLevel += (targetLevel - currentLevel) * 0.35;
  } else {
    currentLevel += (targetLevel - currentLevel) * 0.12;
  }

  const cx = w / 2, cy = h / 2;
  const color = stateColors[currentState] || "#8ba4ff";

  // Bars react proportionally to currentLevel.
  // When near zero, bars are basically invisible (small).
  const bars = 96;
  const innerR = Math.min(w, h) * 0.16;
  const maxBar = Math.min(w, h) * 0.22;
  const baseLen = 3 * DPR;          // minimal length when silent
  const activeAmp = currentLevel * maxBar;

  ctx.lineCap = "round";
  for (let i = 0; i < bars; i++) {
    const angle = (i / bars) * Math.PI * 2 + frame * 0.002;
    // Use only currentLevel-driven shape: per-bar deterministic variation by index
    const variation = 0.55 + 0.45 * Math.sin(i * 0.7 + frame * 0.02);
    const len = baseLen + activeAmp * variation;
    const r1 = innerR;
    const r2 = innerR + len;
    const x1 = cx + Math.cos(angle) * r1;
    const y1 = cy + Math.sin(angle) * r1;
    const x2 = cx + Math.cos(angle) * r2;
    const y2 = cy + Math.sin(angle) * r2;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    const opacityHex = currentLevel > 0.04 ? "" : "44";
    ctx.strokeStyle = color + opacityHex;
    ctx.lineWidth = 1.6 * DPR;
    ctx.shadowColor = color;
    ctx.shadowBlur = currentLevel > 0.05 ? 8 * DPR : 0;
    ctx.stroke();
  }
  ctx.shadowBlur = 0;

  // Outer waveform: only visible when there's activity
  if (currentLevel > 0.02) {
    ctx.beginPath();
    const baseR = Math.min(w, h) * 0.4;
    const points = 200;
    for (let i = 0; i <= points; i++) {
      const angle = (i / points) * Math.PI * 2;
      const wave = Math.sin(angle * 6 + frame * 0.05) * 2 +
                   Math.sin(angle * 11 + frame * 0.08) * 1.5;
      const r = baseR + currentLevel * 60 * DPR + wave * currentLevel * 6 * DPR;
      const x = cx + Math.cos(angle) * r;
      const y = cy + Math.sin(angle) * r;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.4 * DPR;
    ctx.shadowColor = color;
    ctx.shadowBlur = 14 * DPR;
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  if (currentLevel > 0.1 && (currentState === "speaking" || currentState === "listening")) {
    emitParticles(currentLevel);
  }
  drawParticles(color);

  frame++;
  requestAnimationFrame(draw2D);
}

// ===== Liquid/Generative orb (WebGL) =====
// A breathing plasma sphere: fbm-domain-warped edge, fresnel rim, hot star core,
// drifting sparkles. Color palette shifts with the assistant state. Reacts to voice
// level. Falls back to draw2D() above when WebGL is unavailable.
const ORB_VERT = `
attribute vec2 aPos;
void main(){ gl_Position = vec4(aPos, 0.0, 1.0); }`;

const ORB_FRAG = `
precision highp float;
uniform vec2 uRes;
uniform float uTime;
uniform float uLevel;
uniform vec3 uInner;
uniform vec3 uMid;
uniform vec3 uRim;

float hash(vec2 p){ p = fract(p*vec2(123.34,456.21)); p += dot(p,p+45.32); return fract(p.x*p.y); }
float noise(vec2 p){
  vec2 i = floor(p), f = fract(p);
  float a = hash(i), b = hash(i+vec2(1.0,0.0)), c = hash(i+vec2(0.0,1.0)), d = hash(i+vec2(1.0,1.0));
  vec2 u = f*f*(3.0-2.0*f);
  return mix(mix(a,b,u.x), mix(c,d,u.x), u.y);
}
float fbm(vec2 p){
  float v = 0.0, amp = 0.5;
  for(int i=0;i<5;i++){ v += amp*noise(p); p *= 2.0; amp *= 0.5; }
  return v;
}
void main(){
  vec2 uv = (gl_FragCoord.xy - 0.5*uRes) / min(uRes.x, uRes.y);
  float t = uTime * 0.22;
  float r = length(uv);

  float breath = 0.33 + 0.022*sin(uTime*0.9) + uLevel*0.10;
  vec2 q = uv * 2.2;
  float warp = fbm(q + vec2(t, -t*0.7) + fbm(q*1.5 - t)*0.6);
  float edge = breath + (warp - 0.5) * (0.13 + uLevel*0.20);

  float body = smoothstep(edge+0.02, edge-0.07, r);
  float rim  = smoothstep(0.07, 0.0, abs(r - edge));
  float core = smoothstep(breath*0.6, 0.0, r);
  float flow = fbm(q*1.3 + vec2(-t*0.8, t) + warp);

  vec3 col = mix(uMid, uInner, core);
  col = mix(col, uRim, rim*0.9);
  col += uInner * core * (0.55 + 0.45*sin(uTime*1.3));
  col *= body * (0.7 + 0.5*flow);

  float halo = smoothstep(edge+0.40, edge, r) * (1.0 - body);
  col += uRim * halo * (0.22 + uLevel*0.25) * (0.6 + 0.4*sin(uTime*0.7));

  // generative drifting sparkles
  vec2 sp = uv*6.0 + vec2(t*0.6, -t*0.4);
  float spark = pow(noise(sp*3.0 + floor(uTime*1.7)), 28.0);
  col += uRim * spark * 1.4 * smoothstep(0.95, 0.25, r);

  col *= smoothstep(1.15, 0.15, r);
  float a = clamp(max(max(col.r, col.g), col.b), 0.0, 1.0);
  gl_FragColor = vec4(col, a);
}`;

// state -> [innerRGB, midRGB, rimRGB] (0..1). VEGA palette: blue-white star core,
// indigo/violet body, teal-violet rim — distinct from the old cyan HUD.
const ORB_PALETTE = {
  boot:      [[0.85,0.93,1.00],[0.22,0.42,0.95],[0.45,0.55,1.00]],
  loading:   [[0.95,0.90,0.75],[0.85,0.62,0.30],[0.65,0.55,1.00]],
  idle:      [[0.90,0.96,1.00],[0.26,0.46,0.98],[0.52,0.46,1.00]],
  listening: [[1.00,0.94,0.78],[1.00,0.68,0.28],[1.00,0.55,0.35]],
  thinking:  [[1.00,0.92,1.00],[0.66,0.40,1.00],[0.85,0.36,1.00]],
  speaking:  [[0.90,1.00,0.97],[0.18,0.92,0.70],[0.30,0.82,0.85]],
};

let orb = null;
function initOrb() {
  function compile(type, src) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      console.warn("orb shader error:", gl.getShaderInfoLog(s)); return null;
    }
    return s;
  }
  const vs = compile(gl.VERTEX_SHADER, ORB_VERT);
  const fs = compile(gl.FRAGMENT_SHADER, ORB_FRAG);
  if (!vs || !fs) return null;
  const prog = gl.createProgram();
  gl.attachShader(prog, vs); gl.attachShader(prog, fs); gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    console.warn("orb link error:", gl.getProgramInfoLog(prog)); return null;
  }
  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 3,-1, -1,3]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, "aPos");
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE);  // additive glow over the breathing background
  return {
    prog, loc, buf,
    u: {
      res:   gl.getUniformLocation(prog, "uRes"),
      time:  gl.getUniformLocation(prog, "uTime"),
      level: gl.getUniformLocation(prog, "uLevel"),
      inner: gl.getUniformLocation(prog, "uInner"),
      mid:   gl.getUniformLocation(prog, "uMid"),
      rim:   gl.getUniformLocation(prog, "uRim"),
    },
    inner: [0.9,0.96,1.0], mid: [0.26,0.46,0.98], rim: [0.52,0.46,1.0],
  };
}

const _t0 = performance.now();
function lerp3(a, b, k) { a[0]+=(b[0]-a[0])*k; a[1]+=(b[1]-a[1])*k; a[2]+=(b[2]-a[2])*k; }
function drawOrb() {
  // smooth level (fast attack, slow release)
  if (targetLevel > currentLevel) currentLevel += (targetLevel - currentLevel) * 0.35;
  else currentLevel += (targetLevel - currentLevel) * 0.10;

  const pal = ORB_PALETTE[currentState] || ORB_PALETTE.idle;
  lerp3(orb.inner, pal[0], 0.06);
  lerp3(orb.mid,   pal[1], 0.06);
  lerp3(orb.rim,   pal[2], 0.06);

  gl.viewport(0, 0, canvas.width, canvas.height);
  gl.clearColor(0, 0, 0, 0);
  gl.clear(gl.COLOR_BUFFER_BIT);
  gl.useProgram(orb.prog);
  gl.bindBuffer(gl.ARRAY_BUFFER, orb.buf);
  gl.enableVertexAttribArray(orb.loc);
  gl.vertexAttribPointer(orb.loc, 2, gl.FLOAT, false, 0, 0);
  gl.uniform2f(orb.u.res, canvas.width, canvas.height);
  gl.uniform1f(orb.u.time, (performance.now() - _t0) / 1000);
  gl.uniform1f(orb.u.level, currentLevel);
  gl.uniform3fv(orb.u.inner, orb.inner);
  gl.uniform3fv(orb.u.mid, orb.mid);
  gl.uniform3fv(orb.u.rim, orb.rim);
  gl.drawArrays(gl.TRIANGLES, 0, 3);

  frame++;
  requestAnimationFrame(drawOrb);
}

// Dispatcher used by init: prefer the WebGL orb, fall back to the 2D canvas.
function draw() {
  if (gl) {
    orb = initOrb();
    if (orb) {
      requestAnimationFrame(drawOrb);
      return;
    }
    // shader failed: drop to 2D fallback
    gl = null;
    ctx = canvas.getContext("2d");
  }
  document.body.classList.add("no-webgl");  // re-enables the DOM core pulse for 2D
  draw2D();
}

// ----- State / events -----
// Audio ducking: lower music volume when Vega is speaking
let _preDuckVolume = null;
function applyAudioDucking(state) {
  if (state === "speaking" || state === "listening") {
    if (_preDuckVolume === null && !audio.paused && audio.volume > 0.1) {
      _preDuckVolume = audio.volume;
      audio.volume = Math.max(0.08, audio.volume * 0.2);
    }
  } else {
    if (_preDuckVolume !== null) {
      audio.volume = _preDuckVolume;
      _preDuckVolume = null;
    }
  }
}

function setState(state, extra) {
  currentState = state;
  const statusEl = $("status");
  const coreEl = $("core");
  const labelEl = $("state-label");
  let label = STATE_LABEL[state] || state.toUpperCase();
  if (extra && extra.message) label = extra.message.toUpperCase();
  statusEl.textContent = label;
  statusEl.className = "status " + state;
  coreEl.className = "core " + state;
  labelEl.textContent = label;
  // expose state on the HUD container for CSS targeting (waveform visibility)
  const hud = document.querySelector(".hud");
  if (hud) hud.setAttribute("data-state", state);
  applyAudioDucking(state);

  // Hide live transcript when not listening
  const lt = $("live-transcript");
  if (lt) {
    if (state !== "listening") {
      lt.classList.remove("show");
      // clear text after fade
      setTimeout(() => { if (currentState !== "listening") lt.textContent = ""; }, 400);
    }
  }

  // update today-extra
  const desc = {
    idle: "In ascolto. Di' \"Hey Vega\" o batti le mani.",
    listening: "Ti sto ascoltando...",
    thinking: "Sto elaborando...",
    speaking: "Sto rispondendo...",
    loading: "Avvio in corso...",
    boot: "Caricamento sistemi...",
  };
  $("today-extra").textContent = desc[state] || "";
}

let typingTimer = null;
function addMessage(who, text) {
  const div = document.createElement("div");
  div.className = "msg " + (who === "user" ? "user" : "vega");
  const label = document.createElement("div");
  label.className = "who";
  label.textContent = who === "user" ? "TU" : "VEGA";
  const body = document.createElement("div");
  body.className = "text";
  div.appendChild(label);
  div.appendChild(body);
  const transcript = $("transcript");
  transcript.appendChild(div);

  if (who === "vega") {
    typeText(body, text);
  } else {
    body.textContent = text;
  }
  transcript.scrollTop = transcript.scrollHeight;
}

function typeText(el, text) {
  if (typingTimer) clearInterval(typingTimer);
  let i = 0;
  const speed = 15;
  typingTimer = setInterval(() => {
    el.textContent = text.slice(0, ++i);
    $("transcript").scrollTop = $("transcript").scrollHeight;
    if (i >= text.length) {
      clearInterval(typingTimer);
      typingTimer = null;
    }
  }, speed);
}

// Human-readable tool labels (no JSON, no nerd)
const TOOL_LABELS = {
  list_emails: "Sto leggendo le tue email",
  search_emails: "Sto cercando nelle email",
  read_email: "Apro l'email",
  summarize_inbox: "Riassumo la posta",
  get_news: "Leggo le notizie",
  get_weather: "Controllo il meteo",
  wikipedia: "Cerco su Wikipedia",
  system_info: "Controllo il sistema",
  open_application: "Apro l'applicazione",
  take_screenshot: "Scatto uno screenshot",
  analyze_screen: "Sto guardando lo schermo",
  get_time: "Controllo l'ora",
  set_timer: "Imposto un timer",
  set_reminder: "Salvo il promemoria",
  read_clipboard: "Leggo gli appunti",
  write_clipboard: "Copio negli appunti",
  save_note: "Salvo la nota",
  list_notes: "Leggo le note",
  add_todo: "Aggiungo alla lista",
  list_todos: "Controllo la lista",
  complete_todo: "Completo l'attivita'",
  remember_fact: "Memorizzo l'informazione",
  list_facts: "Recupero quello che so",
  calculate: "Eseguo il calcolo",
  find_files: "Cerco tra i file",
  read_pdf: "Leggo il PDF",
  set_volume: "Cambio il volume",
  get_volume: "Controllo il volume",
  mute_audio: "Cambio audio",
  set_brightness: "Cambio luminosita'",
  lock_pc: "Blocco il PC",
  shutdown_pc: "Programmo spegnimento",
  list_windows: "Vedo le finestre aperte",
  focus_window: "Porto in primo piano",
  close_window: "Chiudo la finestra",
  minimize_all: "Mostro il desktop",
  web_search: "Cerco sul web",
  read_webpage: "Leggo la pagina web",
  set_home_location: "Memorizzo la tua citta'",
  set_voice: "Cambio la mia voce",
  set_personality: "Cambio il mio tono",
  index_docs: "Indicizzo i tuoi documenti",
  search_docs: "Cerco nei tuoi documenti",
  list_docs: "Elenco i documenti",
  clear_docs_index: "Pulisco l'indice",
  generate_image: "Genero l'immagine",
  web_images: "Cerco foto sul web",
  set_mode: "Cambio modalita'",
  toggle_startup_music: "Aggiorno musica avvio",
  add_instruction: "Memorizzo una nuova regola",
  list_instructions: "Controllo le regole",
  remove_instruction: "Rimuovo una regola",
  show_settings: "Mostro le impostazioni",
};

function humanizeToolName(name) {
  if (TOOL_LABELS[name]) return TOOL_LABELS[name];
  // Heuristic fallback for any new tool
  return name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function addToolEntry(name, args) {
  const log = $("tools-log");
  const empty = log.querySelector(".tools-empty");
  if (empty) empty.remove();
  const div = document.createElement("div");
  div.className = "tool-entry";
  div.innerHTML = `<span class="t-name">${humanizeToolName(name)}</span>`;
  log.insertBefore(div, log.firstChild);
  while (log.children.length > 8) log.removeChild(log.lastChild);
}

function showToast(text) {
  const t = $("toast");
  t.textContent = text;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 5000);
}

// ---- Streaming message bubble ----
let _streamBubble = null;  // current in-progress vega bubble

function _getOrCreateStreamBubble() {
  if (_streamBubble && _streamBubble.isConnected) return _streamBubble;
  const div = document.createElement("div");
  div.className = "msg vega";
  div.id = "streaming-msg";
  const label = document.createElement("div");
  label.className = "who";
  label.textContent = "VEGA";
  const body = document.createElement("div");
  body.className = "text";
  div.appendChild(label);
  div.appendChild(body);
  $("transcript").appendChild(div);
  _streamBubble = div;
  return div;
}

function appendStreamChunk(chunk) {
  const bubble = _getOrCreateStreamBubble();
  const body = bubble.querySelector(".text");
  // Remove cursor temporarily
  const cur = body.querySelector(".stream-cursor");
  if (cur) cur.remove();
  // Append token/chunk to existing text node (or create one)
  const last = body.lastChild;
  if (last && last.nodeType === Node.TEXT_NODE) {
    last.textContent += chunk;
  } else {
    body.appendChild(document.createTextNode(chunk));
  }
  // Re-add blinking cursor
  const cursor = document.createElement("span");
  cursor.className = "stream-cursor";
  body.appendChild(cursor);
  $("transcript").scrollTop = $("transcript").scrollHeight;
}

function finalizeStreamBubble(fullText) {
  if (_streamBubble && _streamBubble.isConnected) {
    // Replace streamed content with final authoritative text, remove cursor
    const body = _streamBubble.querySelector(".text");
    body.innerHTML = "";
    body.textContent = fullText;
    _streamBubble.removeAttribute("id");
    _streamBubble = null;
  } else {
    // No streaming bubble yet (e.g. shortcut / easter egg path) — add normally
    addMessage("vega", fullText);
  }
  $("transcript").scrollTop = $("transcript").scrollHeight;
}

function showApiDownBanner(message, suggestion) {
  // Rimuovi banner esistente se presente
  const existing = document.getElementById("api-down-banner");
  if (existing) existing.remove();

  const banner = document.createElement("div");
  banner.id = "api-down-banner";
  banner.style.cssText = [
    "position:fixed", "top:0", "left:0", "right:0", "z-index:9999",
    "background:rgba(255,60,60,0.92)", "color:#fff", "padding:10px 20px",
    "display:flex", "align-items:center", "justify-content:space-between",
    "font-size:13px", "letter-spacing:0.05em", "backdrop-filter:blur(4px)"
  ].join(";");

  const left = document.createElement("span");
  left.textContent = "⚠ " + message + (suggestion ? " " + suggestion : "");

  const actions = document.createElement("span");
  actions.style.display = "flex";
  actions.style.gap = "10px";

  const settingsBtn = document.createElement("button");
  settingsBtn.textContent = "Impostazioni";
  settingsBtn.style.cssText = "background:rgba(255,255,255,0.25);border:1px solid rgba(255,255,255,0.5);color:#fff;padding:3px 10px;border-radius:4px;cursor:pointer;font-size:12px;";
  settingsBtn.onclick = () => {
    // Apri il pannello impostazioni se esiste, altrimenti vai a /settings
    const settingsPanel = document.getElementById("settings-panel") || document.getElementById("panel-settings");
    if (settingsPanel) {
      settingsPanel.style.display = "block";
    } else {
      document.getElementById("nav-settings")?.click();
    }
    banner.remove();
  };

  const closeBtn = document.createElement("button");
  closeBtn.textContent = "✕";
  closeBtn.style.cssText = "background:none;border:none;color:#fff;font-size:16px;cursor:pointer;padding:0 4px;";
  closeBtn.onclick = () => banner.remove();

  actions.appendChild(settingsBtn);
  actions.appendChild(closeBtn);
  banner.appendChild(left);
  banner.appendChild(actions);
  document.body.prepend(banner);

  // Auto-dismiss dopo 30s
  setTimeout(() => banner.remove(), 30000);
}

function triggerRipple() {
  const r = $("ripple");
  r.classList.remove("go");
  void r.offsetWidth;
  r.classList.add("go");
}

// ============================================================
// CARDS STAGE - visual responses alongside spoken
// ============================================================
function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

// Image loader with automatic retry (Pollinations can be slow / occasionally fail)
function attachImageLoader(imgId) {
  const img = document.getElementById(imgId);
  const loading = document.getElementById(imgId + "_load");
  if (!img) return;
  const src = img.getAttribute("data-src");
  if (!src) return;

  const startLoad = () => {
    const attempt = Number(img.getAttribute("data-attempt")) || 0;
    img.setAttribute("data-attempt", String(attempt + 1));
    // Cache-buster on retry so browser doesn't reuse failed response
    const url = attempt === 0 ? src : src + (src.includes("?") ? "&" : "?") + "_r=" + Date.now();
    img.onload = () => {
      if (loading) loading.style.display = "none";
      img.classList.add("loaded");
    };
    img.onerror = () => {
      if (attempt < 2) {
        if (loading) loading.textContent = "Riprovo... (" + (attempt + 1) + "/3)";
        setTimeout(startLoad, 2000);
      } else {
        if (loading) {
          loading.innerHTML = "⚠️ Impossibile caricare l'immagine<br><span style='font-size:9px;opacity:0.6'>Pollinations sovraccarico - prova rigenera</span>";
        }
      }
    };
    img.src = url;
  };
  startLoad();
}

function showCard(type, data) {
  console.log("[CARD]", type, data);
  const stage = $("cards-stage");
  if (!stage) {
    console.warn("[CARD] cards-stage element not found!");
    return;
  }
  // Keep max 3 cards visible (cleaner holographic feel)
  while (stage.children.length >= 3) {
    const old = stage.firstChild;
    old.classList.add("out");
    setTimeout(() => { if (old.parentNode) old.remove(); }, 500);
    // Force-detach NOW so we don't exceed limit; allows animation to play
    if (stage.children.length >= 3) stage.removeChild(old);
  }
  const card = document.createElement("div");
  card.className = "card-fly card-" + type;
  let header = "";
  let body = "";
  try {
    if (type === "weather") {
      header = "METEO";
      const fc = (data.forecast || []).slice(0, 4).map(d => {
        const dayStr = d.date ? new Date(d.date).toLocaleDateString("it-IT", {weekday: "short"}) : "";
        return `<div class="wt-day">${escapeHtml(dayStr)}<div class="wt-mm">${escapeHtml(d.min)}° / ${escapeHtml(d.max)}°</div></div>`;
      }).join("");
      body = `
        <div class="wt-top">
          <span class="wt-temp">${escapeHtml(data.temp)}°</span>
          <span class="wt-city">${escapeHtml(data.city)}</span>
        </div>
        <div class="wt-desc">${escapeHtml(data.desc)}</div>
        <div class="wt-detail">
          <span>💧 ${escapeHtml(data.humidity)}%</span>
          <span>💨 ${escapeHtml(data.wind)} km/h</span>
          <span>🌡 percepiti ${escapeHtml(data.feels)}°</span>
        </div>
        ${fc ? `<div class="wt-forecast">${fc}</div>` : ""}
      `;
    } else if (type === "news") {
      header = "NOTIZIE";
      body = (data.items || []).slice(0, 5).map(it => {
        const img = it.image ? `<img class="nw-img" src="${escapeHtml(it.image)}" loading="lazy" onerror="this.style.display='none'">` : "";
        return `
        <div class="nw-item">
          ${img}
          <div class="nw-text">
            <div class="nw-src">${escapeHtml(it.source)}</div>
            <div class="nw-title" data-link="${escapeHtml(it.link || "")}">${escapeHtml(it.title)}</div>
            ${it.summary ? `<div class="nw-summary">${escapeHtml(it.summary)}</div>` : ""}
          </div>
        </div>`;
      }).join("");
    } else if (type === "wikipedia") {
      header = "WIKIPEDIA";
      const imgHtml = data.image
        ? `<img class="wk-image" src="${escapeHtml(data.image)}" alt="${escapeHtml(data.title)}" loading="lazy" onerror="this.style.display='none'">`
        : "";
      body = `
        ${imgHtml}
        <div class="wk-title">${escapeHtml(data.title)}</div>
        <div class="wk-text">${escapeHtml(data.summary)}</div>
        ${data.url ? `<div class="wk-link" data-link="${escapeHtml(data.url)}">apri pagina →</div>` : ""}
      `;
    } else if (type === "stocks") {
      header = "QUOTAZIONI";
      body = (data.items || []).map(it => {
        const dir = it.change_pct >= 0 ? "up" : "down";
        const arrow = it.change_pct >= 0 ? "↑" : "↓";
        return `<div class="st-row">
          <span class="st-tk">${escapeHtml(it.ticker)}</span>
          <span class="st-pr">${escapeHtml(it.price)} ${escapeHtml(it.currency)}</span>
          <span class="st-ch ${dir}">${arrow} ${escapeHtml(it.change_pct)}%</span>
        </div>`;
      }).join("");
    } else if (type === "welcome") {
      header = "BENVENUTO";
      body = `
        <div class="wk-title">${escapeHtml(data.title || "Ciao")}</div>
        <div class="wk-text">${escapeHtml(data.text || "")}</div>
      `;
    } else if (type === "image") {
      header = "IMMAGINE";
      const imgId = "img_" + Math.random().toString(36).slice(2, 8);
      const isPollinations = (data.url || "").includes("pollinations");
      body = `
        <div class="img-prompt">${escapeHtml(data.prompt || "")}</div>
        <div class="gen-img-wrap" id="${imgId}_wrap">
          <div class="gen-img-loading" id="${imgId}_load">
            ${isPollinations ? "Generazione in corso (5-20s)..." : "Caricamento..."}
          </div>
          <img class="gen-img" id="${imgId}" data-src="${escapeHtml(data.url)}"
               data-attempt="0" alt="${escapeHtml(data.prompt)}">
        </div>
        <div class="img-actions">
          <button class="img-btn" data-action="open" data-url="${escapeHtml(data.url)}">Apri full size</button>
          <button class="img-btn" data-action="regen" data-prompt="${escapeHtml(data.prompt)}" data-style="${escapeHtml(data.style || "")}">Rigenera</button>
        </div>
      `;
      // Set up image loading with retry
      setTimeout(() => attachImageLoader(imgId), 50);
    } else if (type === "radio") {
      header = "RADIO";
      body = `
        <div class="wk-title">📻 ${escapeHtml(data.station)}</div>
        <div class="wk-text">Streaming live in corso. Usa il player a destra per pausa/stop.</div>
      `;
      // Tell the player to load this stream
      setTimeout(() => playStreamUrl(data.url, data.station), 100);
    } else if (type === "gallery") {
      header = "GALLERIA FOTO";
      const itemsHtml = (data.items || []).slice(0, 9).map((it, idx) => `
        <div class="gl-item" data-link="${escapeHtml(it.page || it.url)}" title="${escapeHtml(it.title)}">
          <img src="${escapeHtml(it.url)}" loading="lazy" alt="${escapeHtml(it.title)}"
               onerror="this.parentNode.style.display='none'">
          <div class="gl-cap">${escapeHtml(it.title.substring(0, 50))}</div>
        </div>
      `).join("");
      body = `
        <div class="gl-query">"${escapeHtml(data.query)}"</div>
        <div class="gl-grid">${itemsHtml}</div>
      `;
    } else if (type === "chart") {
      header = "GRAFICO";
      const items = data.data || [];
      const maxVal = Math.max(0.001, ...items.map(d => Number(d.value) || 0));
      const barsHtml = items.map(it => {
        const h = ((Number(it.value) || 0) / maxVal) * 100;
        return `<div class="chbar"><div class="chbar-fill" style="height:${h}%" data-tip="${escapeHtml(it.label)}: ${escapeHtml(it.value)}"></div><div class="chbar-label">${escapeHtml(it.label).slice(0, 8)}</div></div>`;
      }).join("");
      body = `
        <div class="ch-title">${escapeHtml(data.title || "")}</div>
        <div class="ch-area">${barsHtml}</div>
        <div class="ch-axis">${escapeHtml(data.x_label || "")} | ${escapeHtml(data.y_label || "")}</div>
      `;
    } else if (type === "docs") {
      header = "NEI TUOI DOCUMENTI";
      const itemsHtml = (data.items || []).slice(0, 5).map(it => `
        <div class="dc-item">
          <div class="dc-file">${escapeHtml(it.file)} <span class="dc-score">${escapeHtml(it.score)}</span></div>
          <div class="dc-snippet">${escapeHtml(it.snippet)}</div>
        </div>
      `).join("");
      body = `<div class="dc-query">"${escapeHtml(data.query)}"</div>${itemsHtml}`;
    } else if (type === "morning_briefing") {
      header = data.title || "MORNING BRIEFING";
      const sect = (label, html) => `<div class="mb-section"><div class="mb-label">${label}</div>${html}</div>`;
      const list = (items, render) => items && items.length
        ? `<ul class="mb-list">${items.map(render).join("")}</ul>`
        : '<div class="mb-empty">—</div>';
      body = `
        <div class="mb-grid">
          ${sect("☀️ METEO", data.weather
            ? `<div class="mb-weather"><span class="mb-temp">${escapeHtml(data.weather.temp || "-")}°</span><span class="mb-city">${escapeHtml(data.weather.city || "")}</span><span class="mb-desc">${escapeHtml(data.weather.desc || "")}</span></div>`
            : '<div class="mb-empty">configura home_location</div>')}
          ${sect("🛡 INCIDENT APERTI", list(data.open_incidents, i =>
            `<li><b>${escapeHtml(i.id)}</b> <span class="mb-tag mb-${escapeHtml(i.classification || "routine")}">${escapeHtml(i.classification || "routine")}</span><br>${escapeHtml(i.title || "")}${i.notification_deadline_hours ? `<br><span class="mb-deadline">⏰ notifica entro ${i.notification_deadline_hours}h</span>` : ''}</li>`))}
          ${sect("📜 PRIVACY (Garante + Federprivacy + EDPB)", list(data.privacy_news, n =>
            `<li>${escapeHtml(n.content)}</li>`))}
          ${sect("🛡 CYBER (CSIRT + CISA + ENISA)", list(data.cyber_news, n =>
            `<li>${escapeHtml(n.content)}</li>`))}
          ${sect("💡 PROPOSTE INNOVATOR", list(data.pending_proposals, p =>
            `<li>${escapeHtml(p.content)}</li>`))}
          ${sect("📋 COMPLIANCE 30gg", data.compliance && Object.keys(data.compliance).length
            ? `<div class="mb-stats">
                 <span><b>${data.compliance.dpo_vetoes || 0}</b> DPO veto</span>
                 <span><b>${data.compliance.incidents_open || 0}</b> incident open</span>
                 <span><b>${data.compliance.shield_injections || 0}</b> injection caught</span>
                 <span><b>${data.compliance.canary_leaks || 0}</b> leak</span>
                 <span><b>${data.compliance.audit_records || 0}</b> audit</span>
               </div>`
            : '<div class="mb-empty">—</div>')}
        </div>
      `;
    } else if (type === "suggestion") {
      header = "SUGGERIMENTO";
      const a = data.action || {};
      const auto = a.automation || {};
      const payload = encodeURIComponent(JSON.stringify(auto));
      body = `
        <div class="sug-title">${escapeHtml(data.title || "Suggerimento")}</div>
        <div class="sug-text">${escapeHtml(data.text || "")}</div>
        ${a.label ? `
          <div class="sug-actions">
            <button class="sug-accept" data-payload="${payload}">✓ ${escapeHtml(a.label)}</button>
            <button class="sug-dismiss">✗ Ignora</button>
          </div>` : ""}
      `;
    } else if (type === "self_healing") {
      header = "SELF-HEALING";
      const samples = (data.samples || []).slice(0, 3).map(s =>
        `<li>${escapeHtml(String(s).slice(0, 140))}</li>`).join("");
      body = `
        <div class="sh-title">${escapeHtml(data.title || "Errore ricorrente")}</div>
        <div class="sh-text">${escapeHtml(data.text || "")}</div>
        ${samples ? `<details class="sh-details"><summary>Esempi (${data.occurrences || 0})</summary><ul>${samples}</ul></details>` : ""}
        <div class="sug-actions"><button class="sug-dismiss">OK, capito</button></div>
      `;
    } else {
      header = type.toUpperCase();
      body = `<div>${escapeHtml(JSON.stringify(data))}</div>`;
    }
  } catch (e) {
    body = `<div>Errore card: ${escapeHtml(e.message)}</div>`;
  }
  card.innerHTML = `
    <div class="ch"><span>${header}</span><span class="cx" title="Chiudi">×</span></div>
    ${body}
  `;
  card.querySelector(".cx").addEventListener("click", () => {
    card.classList.add("out");
    setTimeout(() => card.remove(), 400);
  });
  // Click on title/link opens in browser
  card.querySelectorAll("[data-link]").forEach(el => {
    el.style.cursor = "pointer";
    el.addEventListener("click", () => {
      const url = el.getAttribute("data-link");
      if (url) window.open(url, "_blank");
    });
  });
  // Image card buttons
  card.querySelectorAll(".img-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const action = btn.getAttribute("data-action");
      if (action === "open") {
        window.open(btn.getAttribute("data-url"), "_blank");
      } else if (action === "regen") {
        const prompt = btn.getAttribute("data-prompt");
        const style = btn.getAttribute("data-style");
        fetch("/api/text", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({text: `genera di nuovo l'immagine: ${prompt}${style ? ", stile " + style : ""}`}),
        });
      }
    });
  });
  // Accept/dismiss for suggestion/self_healing cards
  const acceptBtn = card.querySelector(".sug-accept");
  if (acceptBtn) {
    acceptBtn.addEventListener("click", async () => {
      try {
        const auto = JSON.parse(decodeURIComponent(acceptBtn.getAttribute("data-payload") || "{}"));
        const r = await fetch("/api/proactive/accept", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({ automation: auto }),
        });
        const j = await r.json();
        if (j.ok) {
          showToast("Automazione creata");
          playSuccess();
        } else {
          showToast("Errore: " + (j.error || "?"));
        }
      } catch (e) { showToast("Errore: " + e.message); }
      card.classList.add("out");
      setTimeout(() => card.remove(), 400);
    });
  }
  card.querySelectorAll(".sug-dismiss").forEach(b =>
    b.addEventListener("click", () => {
      card.classList.add("out");
      setTimeout(() => card.remove(), 400);
    }));
  stage.appendChild(card);
  // Auto-dismiss after 35 seconds (holographic cards fade naturally)
  setTimeout(() => {
    if (card.parentNode) {
      card.classList.add("out");
      setTimeout(() => card.remove(), 500);
    }
  }, 35000);
}

// ============================================================
// SOUNDBOARD SCI-FI (toggleable via settings)
// Synthesized via Web Audio API - no audio files needed
// ============================================================
let _audioCtx = null;
let _soundsEnabled = true;

function _ctx() {
  _audioCtx = _audioCtx || new (window.AudioContext || window.webkitAudioContext)();
  if (_audioCtx.state === "suspended") _audioCtx.resume();
  return _audioCtx;
}

function _playTones(tones, type = "sine", baseGain = 0.18) {
  if (!_soundsEnabled) return;
  try {
    const ctx = _ctx();
    tones.forEach(({freq, t, dur, gain}) => {
      const osc = ctx.createOscillator();
      const g = ctx.createGain();
      osc.type = type;
      osc.frequency.value = freq;
      const t0 = ctx.currentTime + t;
      g.gain.setValueAtTime(0, t0);
      g.gain.linearRampToValueAtTime(gain || baseGain, t0 + 0.015);
      g.gain.exponentialRampToValueAtTime(0.001, t0 + dur);
      osc.connect(g).connect(ctx.destination);
      osc.start(t0);
      osc.stop(t0 + dur + 0.05);
    });
  } catch (e) {}
}

function playWakeBeep() {
  _playTones([
    {freq: 880, t: 0, dur: 0.12},
    {freq: 1320, t: 0.08, dur: 0.12},
  ], "sine", 0.18);
}

function playSuccess() {
  _playTones([
    {freq: 660, t: 0, dur: 0.1},
    {freq: 880, t: 0.06, dur: 0.1},
    {freq: 1100, t: 0.12, dur: 0.15},
  ], "sine", 0.14);
}

function playError() {
  _playTones([
    {freq: 220, t: 0, dur: 0.18},
    {freq: 180, t: 0.1, dur: 0.22},
  ], "sawtooth", 0.16);
}

function playNotification() {
  _playTones([
    {freq: 1320, t: 0, dur: 0.08, gain: 0.12},
    {freq: 1760, t: 0.05, dur: 0.1, gain: 0.10},
  ], "triangle");
}

function playBoot() {
  _playTones([
    {freq: 220, t: 0, dur: 0.3},
    {freq: 440, t: 0.15, dur: 0.3},
    {freq: 880, t: 0.3, dur: 0.4},
  ], "sine", 0.10);
}

function playClick() {
  _playTones([{freq: 2000, t: 0, dur: 0.04, gain: 0.08}], "square");
}

// Sync sounds_enabled from settings
async function syncSoundsEnabled() {
  try {
    const r = await fetch("/api/settings");
    const p = await r.json();
    _soundsEnabled = p.sounds_enabled !== false;
  } catch (e) {}
}
syncSoundsEnabled();

// ----- Clock -----
function updateClock() {
  const d = new Date();
  $("clock").textContent = d.toLocaleTimeString("it-IT");
  $("date").textContent = d.toLocaleDateString("it-IT", { weekday: "short", day: "numeric", month: "short" });
  $("today-day").textContent = d.toLocaleDateString("it-IT", { weekday: "long" });
  $("today-date").textContent = d.toLocaleDateString("it-IT", { day: "numeric", month: "long" });
}
setInterval(updateClock, 1000);
updateClock();

// ----- Weather (proxied through server to avoid CORS in Chrome app mode) -----
async function loadWeather() {
  try {
    const r = await fetch("/api/weather");
    const text = await r.text();
    let d;
    try { d = JSON.parse(text); } catch (pe) {
      throw new Error("JSON parse error: " + text.slice(0, 80));
    }
    if (!r.ok || d.error) throw new Error(d.error || "HTTP " + r.status);
    const cur = d.current_condition?.[0];
    const area = d.nearest_area?.[0];
    if (!cur || !area) throw new Error("struttura dati inattesa");
    $("w-temp").textContent = (cur.temp_C ?? "?") + "°";
    $("w-desc").textContent = (cur.lang_it?.[0]?.value || cur.weatherDesc?.[0]?.value || "").toLowerCase();
    $("w-loc").textContent = (area.areaName?.[0]?.value || "").toUpperCase();
  } catch (e) {
    console.error("[weather]", e.message);
    const desc = $("w-desc");
    if (desc) desc.textContent = "err: " + e.message.slice(0, 40);
  }
}
loadWeather();
// Riprova dopo 30s se al primo carico non ha dati (server potrebbe ancora avviarsi)
setTimeout(() => { if (!$("w-temp")?.textContent?.match(/\d/)) loadWeather(); }, 30000);
setInterval(loadWeather, 600000);

// ----- Mic meter -----
function updateMic(rms) {
  const pct = Math.min(100, rms * 600);
  $("mic-fill").style.width = pct + "%";
  const db = rms > 0.0001 ? (20 * Math.log10(rms)).toFixed(0) : -60;
  $("mic-label").textContent = db + " dB";
}

// ----- Refresh todos / notes -----
async function refreshState() {
  try {
    const r = await fetch("/api/state");
    const d = await r.json();
    const todoEl = $("todos");
    const noteEl = $("notes");
    todoEl.innerHTML = "";
    noteEl.innerHTML = "";
    if (!d.todos || !d.todos.length) {
      todoEl.innerHTML = '<div class="tools-empty">Niente in lista</div>';
    } else {
      d.todos.filter(t => !t.done).slice(0, 8).forEach(t => {
        const div = document.createElement("div");
        div.className = "todo-item";
        div.textContent = t.text;
        todoEl.appendChild(div);
      });
    }
    if (!d.notes || !d.notes.length) {
      noteEl.innerHTML = '<div class="tools-empty">Nessuna nota</div>';
    } else {
      d.notes.slice().reverse().forEach(n => {
        const div = document.createElement("div");
        div.className = "note-item";
        div.textContent = n.text;
        noteEl.appendChild(div);
      });
    }
  } catch (e) {}
}
setInterval(refreshState, 8000);
refreshState();

// ----- Usage / cost widget -----
async function refreshUsage() {
  try {
    const r = await fetch("/api/usage");
    const d = await r.json();
    const today = d.today || {};
    const total = d.total || {};
    $("u-today").textContent = "$" + (d.today_cost_usd || 0).toFixed(4);
    $("u-total").textContent = "$" + (d.total_cost_usd || 0).toFixed(4);
    const cw = today.cache_write || 0;
    const cr = today.cache_read || 0;
    const ti = today.input || 0;
    const hitRate = (cr + ti + cw) > 0 ? (cr / (cr + ti + cw) * 100).toFixed(0) : 0;
    const cacheEl = $("u-cache");
    cacheEl.textContent = hitRate + "%";
    cacheEl.classList.toggle("good", hitRate >= 50);
    $("u-calls").textContent = (today.calls || 0) + " chiamate";
    const totalTok = (today.input || 0) + (today.output || 0) + (today.cache_read || 0) + (today.cache_write || 0);
    $("u-tokens").textContent = totalTok.toLocaleString("it-IT") + " tok";
  } catch (e) {}
}
setInterval(refreshUsage, 5000);
refreshUsage();

// ----- Boot sequence -----
const bootLines = [
  ["INIZIALIZZAZIONE SISTEMA", "OK"],
  ["RICONOSCIMENTO VOCALE", "OK"],
  ["WAKE WORD ENGINE", "OK"],
  ["INTELLIGENZA ARTIFICIALE", "OK"],
  ["MEMORIA PERSISTENTE", "OK"],
  ["FEED INFORMATIVI", "OK"],
  ["INTERFACCIA UTENTE", "OK"],
  ["TUTTI I SISTEMI ONLINE", "READY"],
];

function runBootSequence() {
  const log = $("boot-log");
  bootLines.forEach((line, i) => {
    setTimeout(() => {
      const div = document.createElement("div");
      div.className = "line";
      div.style.animationDelay = "0s";
      div.innerHTML = `&gt; ${line[0]}<span class="ok">[${line[1]}]</span>`;
      log.appendChild(div);
    }, i * 260);
  });
  setTimeout(() => {
    $("boot").classList.add("hide");
    resize();
  }, bootLines.length * 260 + 900);
}
runBootSequence();
resize();
draw();
resizeWaveform();
drawWaveform();

// Welcome test card removed - no longer needed.

// ----- WebSocket -----
let ws = null;
function connect() {
  const wsProto = location.protocol === "https:" ? "wss" : "ws";
  const wsUrl = `${wsProto}://${location.host}/ws` +
                (VEGA_TOKEN ? `?token=${encodeURIComponent(VEGA_TOKEN)}` : "");
  ws = new WebSocket(wsUrl);
  ws.onmessage = (ev) => {
    const data = JSON.parse(ev.data);

    if (data.event === "state") {
      setState(data.payload.state, data.payload);
      _updateMicHud(data.payload.state);
    } else if (data.event === "level") {
      // Direct map from RMS to visual level, with clear silence threshold
      const rms = data.payload.rms;
      targetLevel = rms < 0.005 ? 0 : Math.min(1, (rms - 0.005) * 7);
      updateMic(rms);
    } else if (data.event === "stream_token") {
      // Append sentence chunk to streaming bubble (sentence by sentence, synced with TTS)
      appendStreamChunk(data.payload.text);
    } else if (data.event === "text") {
      if (data.payload.who === "vega") {
        // Finalize streaming bubble (or create normal bubble if no streaming)
        finalizeStreamBubble(data.payload.text);
      } else {
        addMessage(data.payload.who, data.payload.text);
      }
    } else if (data.event === "tool") {
      addToolEntry(data.payload.name, data.payload.args);
    } else if (data.event === "tool_progress") {
      _renderToolProgress(data.payload);
    } else if (data.event === "wake") {
      triggerRipple();
      playWakeBeep();
      const src = data.payload && data.payload.source;
      if (src === "manual") showToast("Sveglia manuale");
      else if (src === "voice-it") showToast("Sveglia in italiano");
    } else if (data.event === "card") {
      showCard(data.payload.type, data.payload.data);
    } else if (data.event === "team_message") {
      // Live team agent message (Automation Mode)
      const stream = $("team-stream");
      if (stream) {
        const wrap = document.createElement("div");
        wrap.innerHTML = _renderTeamMsg(data.payload);
        const node = wrap.firstChild;
        if (node) stream.insertBefore(node, stream.firstChild);
        while (stream.children.length > 60) stream.removeChild(stream.lastChild);
      }
      // Visual pulse on the source agent tile
      const from = (data.payload?.from || "").replace("agent.", "");
      const tile = $(`agent-tile-${from}`);
      if (tile) {
        tile.classList.add("active-pulse");
        setTimeout(() => tile.classList.remove("active-pulse"), 700);
      }
    } else if (data.event === "agent_progress") {
      handleAgentProgress(data.payload);
    } else if (data.event === "voice_interrupt") {
      showToast("Interrotto");
    } else if (data.event === "partial_transcript") {
      const lt = $("live-transcript");
      lt.textContent = data.payload.text || "";
      lt.classList.add("show");
    } else if (data.event === "reload") {
      // Hot reload: a UI file was modified, refresh the page
      console.log("[hot-reload]", data.payload.file);
      // Small delay so toast can show briefly
      showToast("UI aggiornata: ricarico");
      setTimeout(() => location.reload(), 600);
    } else if (data.event === "music") {
      const ev = data.payload.event;
      if (ev === "start" && data.payload.url) {
        playBootMusic();
      } else if (ev === "stop") {
        // Engine asks us to make room for spoken response
        try { audio.pause(); } catch (e) {}
        $("pc-play").textContent = "▶";
        $("np-artist").textContent = "in pausa";
        isPlayingIntro = false;
      } else if (ev === "play") {
        togglePlay();
      }
    } else if (data.event === "vega_active") {
      vegaActive = !!data.payload.active;
      updatePauseButton();
    } else if (data.event === "notification") {
      showToast(data.payload.text);
      playNotification();
      setTimeout(refreshState, 500);
    } else if (data.event === "error") {
      addMessage("vega", "[Errore] " + data.payload.message);
      playError();
      document.body.classList.add("glitching");
      setTimeout(() => document.body.classList.remove("glitching"), 1100);
    } else if (data.event === "api_down") {
      // API Anthropic irraggiungibile — mostra banner con link impostazioni
      const p = data.payload || {};
      showApiDownBanner(p.message || "API non raggiungibile", p.suggestion || "");
    } else if (data.event === "cache_hit") {
      showToast("💾 Cache: " + (data.payload.tool || "tool"));
    }
  };
  ws.onclose = () => setTimeout(connect, 1500);
}
connect();

// ----- Text input -----
function sendText() {
  const inp = $("text-input");
  const t = inp.value.trim();
  if (!t) return;
  inp.value = "";
  fetch("/api/text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: t }),
  });
}

$("send-btn").addEventListener("click", sendText);

const textInput = $("text-input");
textInput.addEventListener("keydown", (e) => {
  // Enter = send, Shift+Enter = newline
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendText();
  }
});
// Auto-grow textarea up to max-height
textInput.addEventListener("input", () => {
  textInput.style.height = "auto";
  textInput.style.height = Math.min(textInput.scrollHeight, 140) + "px";
});

$("stop-btn").addEventListener("click", () => {
  fetch("/api/interrupt", { method: "POST" });
});

$("wake-btn").addEventListener("click", () => {
  fetch("/api/wake", { method: "POST" });
});

$("fs-btn").addEventListener("click", () => {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {});
  } else {
    document.exitFullscreen().catch(() => {});
  }
});

// ============================================================
// SETTINGS MODAL
// ============================================================
function openModal(id) { document.getElementById(id).classList.add("show"); }
function closeModal(id) { document.getElementById(id).classList.remove("show"); }

document.querySelectorAll(".modal-close").forEach(btn => {
  btn.addEventListener("click", () => closeModal(btn.getAttribute("data-close")));
});
document.querySelectorAll(".modal").forEach(m => {
  m.addEventListener("click", (e) => { if (e.target === m) m.classList.remove("show"); });
});

async function loadSettings() {
  try {
    const r = await fetch("/api/settings");
    const p = await r.json();
    $("set-voice").value = p.voice || "it-IT-GiuseppeNeural";
    $("set-voice-rate").value = p.voice_rate || "-3%";
    $("set-personality").value = p.personality || "friendly";
    $("set-mode").value = p.mode || "general";
    $("set-home").value = p.home_location || "";
    $("set-music").checked = !!p.startup_music;
    $("set-sounds").checked = p.sounds_enabled !== false;
    $("set-privacy").checked = !!p.privacy_mode;
    const vi = $("set-voice-interrupt");
    if (vi) vi.checked = !!p.voice_interrupt;
    const ao = $("set-always-on");
    if (ao) ao.checked = !!p.always_on;
    const lb = $("set-local-brain");
    if (lb) lb.checked = !!p.local_brain_enabled;
    const tm = $("set-team-mode");
    if (tm) tm.checked = !!p.team_mode;
    const svt = $("set-sync-voice-text");
    if (svt) svt.checked = p.sync_voice_text !== false;  // default true
    // Probe Ollama status
    try {
      const r2 = await fetch("/api/local_brain/status");
      const st = await r2.json();
      const lbl = $("set-local-status");
      if (lbl) {
        if (st.available) {
          lbl.textContent = `— online: ${st.current_model || "?"}`;
          lbl.style.color = "var(--hud-green, #7cffa1)";
        } else {
          lbl.textContent = "— offline (avvia Ollama localhost:11434)";
          lbl.style.color = "var(--hud-text-dim, #888)";
        }
      }
    } catch (e) {}
  } catch (e) {}
}

$("settings-btn").addEventListener("click", async () => {
  await loadSettings();
  openModal("settings-modal");
});

// Proposte panel
async function loadProposals() {
  const body = $("prop-body");
  body.innerHTML = "<div style='opacity:.6'>Caricamento...</div>";
  try {
    const r = await fetch("/api/instructions");
    const j = await r.json();
    const items = j.items || [];
    if (!items.length) {
      body.innerHTML = "<div style='opacity:.6;padding:20px;text-align:center'>Nessuna proposta al momento. Vega ti segnalerà qui i pattern rilevati e i fix automatici.</div>";
      return;
    }
    body.innerHTML = items.map(it => `
      <div class="prop-item" data-id="${escapeHtml(it.id || "")}">
        <div class="prop-meta">
          <span class="prop-source">${escapeHtml(it.source || "?")}</span>
          <span class="prop-date">${it.created_at ? new Date(it.created_at * 1000).toLocaleString("it-IT") : ""}</span>
        </div>
        <div class="prop-content">${escapeHtml(it.content || "")}</div>
        <div class="prop-actions">
          <button class="prop-delete" data-id="${escapeHtml(it.id || "")}">Elimina</button>
        </div>
      </div>
    `).join("");
    body.querySelectorAll(".prop-delete").forEach(b => {
      b.addEventListener("click", async () => {
        await fetch("/api/instructions/" + b.getAttribute("data-id"), { method: "DELETE" });
        loadProposals();
      });
    });
  } catch (e) {
    body.innerHTML = "<div style='color:#f66'>Errore: " + escapeHtml(e.message) + "</div>";
  }
}

const propBtn = $("prop-btn");
if (propBtn) {
  propBtn.addEventListener("click", () => {
    openModal("prop-modal");
    loadProposals();
  });
}


// ============ Morning Briefing ============
async function _checkMorningBriefing() {
  try {
    const r = await fetch("/api/briefing/morning");
    const j = await r.json();
    if (!j.should_show) return;
    const payload = j.briefing;
    if (!payload || !payload.data) return;
    // Show as big card
    showCard("morning_briefing", payload.data);
    // Mark shown
    fetch("/api/briefing/mark_shown", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: j.client_id }),
    });
  } catch (e) {
    console.warn("[briefing]", e);
  }
}
// Trigger 4 seconds after boot (let agents warm up)
setTimeout(_checkMorningBriefing, 4000);


// ============ Automation Mode (team agentico) ============
const TIER_LABELS = ["GOVERNANCE", "COMPLIANCE", "OPERATIONS", "INTELLIGENCE"];

let _selectedAgentName = null;

async function loadTeamStatus() {
  try {
    const r = await fetch("/api/team/status");
    const j = await r.json();
    const agents = j.agents || [];
    // 5 tier (was 4): now monitors hanno tier 4
    for (let t = 0; t < 5; t++) {
      const col = $(`tier-${t}-agents`);
      if (!col) continue;
      const agentsHere = agents.filter(a => a.tier === t);
      col.innerHTML = agentsHere.map(a => `
        <div class="org-tile ${a.enabled ? '' : 'disabled'}" id="org-tile-${a.name}" data-name="${a.name}">
          <div class="org-tile-dot ${a.enabled ? '' : 'off'}"></div>
          <span class="org-tile-icon">${a.icon || '🤖'}</span>
          <span class="org-tile-name">${a.name.toUpperCase()}</span>
        </div>
      `).join("");
    }
    // Click → open detail
    document.querySelectorAll(".org-tile").forEach(tile => {
      tile.addEventListener("click", () => {
        const name = tile.getAttribute("data-name");
        document.querySelectorAll(".org-tile").forEach(t => t.classList.remove("selected"));
        tile.classList.add("selected");
        _selectAgentForDetail(name);
        // Switch to detail tab
        document.querySelector('.auto-tab[data-view="detail"]')?.click();
      });
    });
  } catch (e) {
    console.error("loadTeamStatus", e);
  }
}

async function _selectAgentForDetail(name) {
  _selectedAgentName = name;
  $("detail-empty").hidden = true;
  $("detail-content").hidden = false;
  try {
    const r = await fetch(`/api/team/dashboard/${name}`);
    const j = await r.json();
    if (!j.ok) {
      $("detail-name").textContent = "Errore: " + (j.error || "?");
      return;
    }
    const d = j.data;
    $("detail-icon").textContent = d.icon || "🤖";
    $("detail-name").textContent = d.name.toUpperCase();
    $("detail-desc").textContent = d.description || "";
    $("detail-meta").innerHTML = `
      Tier <b>${d.tier}</b> · Model <b>${d.model_pref}</b> ·
      ${d.schedule ? `Schedule <b>${escapeHtml(d.schedule)}</b> · ` : ''}
      Tasks <b>${d.task_count}</b>
    `;
    $("detail-status-dot").className = "detail-status-dot " + (d.enabled ? "" : "off");
    $("detail-toggle").textContent = d.enabled ? "PAUSA" : "RIATTIVA";
    $("detail-toggle").onclick = async () => {
      const op = d.enabled ? "disable" : "enable";
      await fetch(`/api/team/${name}/${op}`, { method: "POST" });
      _selectAgentForDetail(name);
      loadTeamStatus();
    };
    // Hierarchy
    const h = d.hierarchy || {};
    $("detail-hierarchy").innerHTML = `
      <div class="detail-hierarchy-row"><span>Superior</span><b>${escapeHtml(h.superior || '—')}</b></div>
      <div class="detail-hierarchy-row"><span>Tier</span><b>${h.tier ?? d.tier}</b></div>
      ${h.subordinates && h.subordinates.length ?
        `<div class="detail-hierarchy-row"><span>Subordinates</span><b>${h.subordinates.length}</b></div>
         <div style="margin-top:6px;font-size:0.82em;color:var(--hud-text-dim)">${h.subordinates.slice(0,8).map(escapeHtml).join(' · ')}${h.subordinates.length > 8 ? ' ...' : ''}</div>`
        : ''}
      ${h.can_veto ? `<div class="detail-hierarchy-row"><span>Veto power</span><b style="color:var(--hud-red)">SÌ</b></div>` : ''}
      ${h.watches ? `<div class="detail-hierarchy-row"><span>Watches</span><b>${h.watches.length} agents</b></div>` : ''}
      ${h.feeds ? `<div class="detail-hierarchy-row"><span>Feeds</span><b>${h.feeds.join(', ')}</b></div>` : ''}
      ${h.collaborates_with ? `<div class="detail-hierarchy-row"><span>Collab</span><b>${h.collaborates_with.join(', ')}</b></div>` : ''}
    `;
    // Actions
    const acts = d.actions || [];
    $("detail-actions").innerHTML = acts.length === 0
      ? '<div style="opacity:.6;font-size:.85em">Nessuna azione dichiarata</div>'
      : acts.map(a => `
          <button class="detail-action-btn" data-action="${escapeHtml(a.name)}"
                  title="${escapeHtml(a.description || '')}">
            ▶ ${escapeHtml(a.name)}
          </button>
        `).join('') + '<div id="detail-action-result-box"></div>';
    document.querySelectorAll("#detail-actions .detail-action-btn").forEach(b => {
      b.addEventListener("click", async () => {
        const action = b.getAttribute("data-action");
        b.disabled = true;
        b.textContent = `⏳ ${action}`;
        try {
          const r2 = await fetch(`/api/team/${name}/action`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action, args: {} }),
          });
          const j2 = await r2.json();
          let box = $("detail-action-result-box");
          if (box) {
            box.innerHTML = `<div class="detail-action-result">${escapeHtml(JSON.stringify(j2, null, 2))}</div>`;
          }
        } catch (e) {
          showToast("Errore: " + e.message);
        } finally {
          b.disabled = false;
          b.textContent = `▶ ${action}`;
        }
      });
    });
    // Metrics
    const lastActSec = d.last_activity_ts ?
      Math.floor((Date.now() / 1000 - d.last_activity_ts)) : null;
    $("detail-metrics").innerHTML = `
      <div class="detail-hierarchy-row"><span>Stato</span><b>${d.enabled ? '🟢 attivo' : '⚪ pausa'}</b></div>
      <div class="detail-hierarchy-row"><span>Tasks totali</span><b>${d.task_count}</b></div>
      <div class="detail-hierarchy-row"><span>Ultima attività</span><b>${lastActSec !== null ? _timeAgoSec(lastActSec) : '—'}</b></div>
      <div class="detail-hierarchy-row"><span>Model</span><b>${d.model_pref}</b></div>
    `;
    // Wire quickchat
    const qcSend = $("detail-quickchat-send");
    const qcInput = $("detail-quickchat-input");
    qcSend.onclick = async () => {
      const msg = qcInput.value.trim();
      if (!msg) return;
      $("detail-quickchat-output").textContent = "⏳ ...";
      try {
        const r2 = await fetch("/api/team/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ agent: name, message: msg }),
        });
        const j2 = await r2.json();
        $("detail-quickchat-output").textContent = j2.reply || j2.error || "(no reply)";
        qcInput.value = "";
      } catch (e) {
        $("detail-quickchat-output").textContent = "Errore: " + e.message;
      }
    };
    qcInput.onkeydown = (e) => {
      if (e.key === "Enter") { e.preventDefault(); qcSend.click(); }
    };
  } catch (e) {
    console.error("detail load", e);
  }
}

function _timeAgoSec(sec) {
  if (sec < 60) return `${Math.floor(sec)}s fa`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m fa`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h fa`;
  return `${Math.floor(sec / 86400)}g fa`;
}

async function loadTeamOverview() {
  try {
    const r = await fetch("/api/team/overview");
    const j = await r.json();
    const ov = j.overview || {};
    const all = ov.agents || [];
    $("ov-total").textContent = ov.total || all.length;
    $("ov-active").textContent = ov.active_last_5min || 0;
    $("ov-disabled").textContent = all.filter(a => !a.enabled).length;
    $("ov-tasks").textContent = all.reduce((s, a) => s + (a.tasks || 0), 0);
    // Top active
    const top = all.filter(a => a.tasks > 0).sort((a, b) => b.tasks - a.tasks).slice(0, 10);
    $("ov-top-active").innerHTML = top.length === 0
      ? '<div style="opacity:.6">Nessuna attività registrata</div>'
      : top.map(a => `
        <div class="overview-list-item">
          <span>${a.icon || '🤖'} ${escapeHtml(a.name)}</span>
          <b>${a.tasks} task</b>
        </div>`).join("");
    // Inactive >1h
    const inactive = all.filter(a => a.enabled &&
      (a.last_active_sec === null || a.last_active_sec > 3600));
    $("ov-inactive").innerHTML = inactive.length === 0
      ? '<div style="opacity:.6">Tutti recenti</div>'
      : inactive.slice(0, 8).map(a => `
        <div class="overview-list-item">
          <span>${a.icon || '🤖'} ${escapeHtml(a.name)}</span>
          <b style="color:var(--hud-text-mute)">${a.last_active_sec === null ? 'mai' : _timeAgoSec(a.last_active_sec)}</b>
        </div>`).join("");
    // Recent
    const recent = all.filter(a => a.last_active_sec !== null)
      .sort((a, b) => a.last_active_sec - b.last_active_sec).slice(0, 8);
    $("ov-recent").innerHTML = recent.map(a => `
      <div class="overview-list-item">
        <span>${a.icon || '🤖'} ${escapeHtml(a.name)}</span>
        <b>${_timeAgoSec(a.last_active_sec)}</b>
      </div>`).join("");
  } catch (e) { console.error("overview", e); }
}

function _timeAgo(ms) {
  const sec = Math.max(0, (Date.now() - ms) / 1000);
  if (sec < 60) return `${Math.floor(sec)}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h`;
  return `${Math.floor(sec / 86400)}d`;
}

async function loadTeamMessages() {
  try {
    const r = await fetch("/api/team/messages");
    const j = await r.json();
    const stream = $("team-stream");
    if (!stream) return;
    stream.innerHTML = (j.messages || []).slice(-50).reverse().map(m => _renderTeamMsg(m)).join("");
  } catch (e) {}
}

function _renderTeamMsg(m) {
  const ts = m.ts ? new Date(m.ts).toLocaleTimeString("it-IT") : "";
  const from = (m.from || "").replace("agent.", "");
  const kind = m.kind || "?";
  const dataStr = JSON.stringify(m.data || {}).slice(0, 140);
  return `<div class="team-msg kind-${escapeHtml(kind)}">
    <div><span class="msg-from">${escapeHtml(from)}</span> · <span class="msg-kind">${escapeHtml(kind)}</span> · <span style="opacity:.55">${ts}</span></div>
    <div class="msg-data">${escapeHtml(dataStr)}</div>
  </div>`;
}

const automationBtn = $("automation-btn");
if (automationBtn) {
  automationBtn.addEventListener("click", () => {
    openModal("automation-modal");
    loadTeamStatus();
    loadTeamMessages();
    loadChatPersonas();
  });
}

// Tab switching inside Automation modal
const _AUTO_VIEWS = ["board", "detail", "chat", "overview"];
document.querySelectorAll(".auto-tab").forEach(t => {
  t.addEventListener("click", () => {
    document.querySelectorAll(".auto-tab").forEach(x => x.classList.remove("active"));
    t.classList.add("active");
    const view = t.getAttribute("data-view");
    _AUTO_VIEWS.forEach(v => {
      document.querySelectorAll(`.modal-body[data-view="${v}"]`).forEach(el => {
        el.style.display = (v === view) ? "" : "none";
      });
    });
    if (view === "overview") loadTeamOverview();
  });
});

// ============ Agent Chat (Conversation Tabs) ============
let _currentChatAgent = null;

async function loadChatPersonas() {
  try {
    const r = await fetch("/api/team/personas");
    const j = await r.json();
    const col = $("chat-personas");
    if (!col) return;
    col.innerHTML = (j.personas || []).map(p => `
      <div class="chat-persona" data-name="${escapeHtml(p.name)}">
        <span>${p.icon}</span>
        <div>
          <div class="chat-persona-name">${escapeHtml(p.title || p.name)}</div>
        </div>
      </div>
    `).join("");
    col.querySelectorAll(".chat-persona").forEach(el => {
      el.addEventListener("click", () => _selectChatAgent(el.getAttribute("data-name")));
    });
  } catch (e) { console.warn("chat personas", e); }
}

async function _selectChatAgent(name) {
  _currentChatAgent = name;
  document.querySelectorAll(".chat-persona").forEach(el =>
    el.classList.toggle("active", el.getAttribute("data-name") === name));
  const header = $("chat-header");
  if (header) header.querySelector("span").textContent = `💬 ${name.toUpperCase()}`;
  // Load history
  try {
    const r = await fetch(`/api/team/chat/${name}/history`);
    const j = await r.json();
    _renderChatMessages(j.messages || []);
  } catch (e) {}
}

function _renderChatMessages(msgs) {
  const wrap = $("chat-messages");
  if (!wrap) return;
  wrap.innerHTML = msgs.map(m =>
    `<div class="chat-msg ${escapeHtml(m.role)}">${escapeHtml(m.content)}</div>`
  ).join("");
  wrap.scrollTop = wrap.scrollHeight;
}

async function _sendChat() {
  if (!_currentChatAgent) {
    showToast("Seleziona prima un agente");
    return;
  }
  const input = $("chat-input");
  const msg = (input?.value || "").trim();
  if (!msg) return;
  input.value = "";
  const wrap = $("chat-messages");
  // Optimistic user msg
  const userDiv = document.createElement("div");
  userDiv.className = "chat-msg user";
  userDiv.textContent = msg;
  wrap.appendChild(userDiv);
  const thinkDiv = document.createElement("div");
  thinkDiv.className = "chat-msg thinking";
  thinkDiv.textContent = "...";
  wrap.appendChild(thinkDiv);
  wrap.scrollTop = wrap.scrollHeight;
  try {
    const r = await fetch("/api/team/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent: _currentChatAgent, message: msg }),
    });
    const j = await r.json();
    thinkDiv.remove();
    if (j.ok) {
      const replyDiv = document.createElement("div");
      replyDiv.className = "chat-msg assistant";
      replyDiv.textContent = j.reply;
      wrap.appendChild(replyDiv);
      wrap.scrollTop = wrap.scrollHeight;
    } else {
      thinkDiv.textContent = "errore: " + (j.error || "?");
      wrap.appendChild(thinkDiv);
    }
  } catch (e) {
    thinkDiv.textContent = "errore di rete: " + e.message;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const sendBtn = $("chat-send");
  if (sendBtn) sendBtn.addEventListener("click", _sendChat);
  const clearBtn = $("chat-clear");
  if (clearBtn) {
    clearBtn.addEventListener("click", async () => {
      if (!_currentChatAgent) return;
      await fetch(`/api/team/chat/${_currentChatAgent}/clear`, { method: "POST" });
      _renderChatMessages([]);
    });
  }
  const input = $("chat-input");
  if (input) {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        _sendChat();
      }
    });
  }
});

// Live: handle team_message WS event
const _origHandleStateRef = window._origStateRef;

$("set-save").addEventListener("click", async () => {
  const payload = {
    voice: $("set-voice").value,
    voice_rate: $("set-voice-rate").value,
    personality: $("set-personality").value,
    mode: $("set-mode").value,
    home_location: $("set-home").value.trim(),
    startup_music: $("set-music").checked,
    sounds_enabled: $("set-sounds").checked,
    privacy_mode: $("set-privacy").checked,
    voice_interrupt: ($("set-voice-interrupt") ? $("set-voice-interrupt").checked : false),
    always_on: ($("set-always-on") ? $("set-always-on").checked : false),
    local_brain_enabled: ($("set-local-brain") ? $("set-local-brain").checked : false),
    team_mode: ($("set-team-mode") ? $("set-team-mode").checked : false),
    sync_voice_text: ($("set-sync-voice-text") ? $("set-sync-voice-text").checked : true),
  };
  await fetch("/api/settings", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  _soundsEnabled = $("set-sounds").checked;
  playSuccess();
  showToast("Impostazioni salvate");
  closeModal("settings-modal");
});

// ============================================================
// STATS DASHBOARD
// ============================================================
async function loadStats() {
  const body = $("stats-body");
  body.innerHTML = "Caricamento...";
  try {
    const r = await fetch("/api/stats");
    const s = await r.json();

    // Build bar chart for last 14 days cost
    const maxCost = Math.max(0.001, ...(s.history || []).map(d => d.cost));
    const barsHtml = (s.history || []).map(d => {
      const heightPct = Math.max(2, (d.cost / maxCost) * 100);
      const dayLabel = d.date.slice(-5); // MM-DD
      return `<div class="ch-bar" style="height:${heightPct}%" data-tip="${dayLabel}: $${d.cost.toFixed(4)} (${d.calls} call)"></div>`;
    }).join("");
    const axisHtml = (s.history || []).map(d => `<span>${d.date.slice(-2)}</span>`).join("");

    body.innerHTML = `
      <div class="stats-grid">
        <div class="stat-card"><div class="v">$${s.total_cost_usd.toFixed(2)}</div><div class="l">Speso totale</div></div>
        <div class="stat-card"><div class="v">${s.total_calls}</div><div class="l">Chiamate AI</div></div>
        <div class="stat-card"><div class="v">${s.cache_hit_pct}%</div><div class="l">Cache hit oggi</div></div>
        <div class="stat-card"><div class="v">${s.todos_open}</div><div class="l">Todo aperti</div></div>
        <div class="stat-card"><div class="v">${s.notes_count}</div><div class="l">Note salvate</div></div>
        <div class="stat-card"><div class="v">${s.facts_count}</div><div class="l">Fatti su di te</div></div>
        <div class="stat-card"><div class="v">${s.conversations_logged}</div><div class="l">Scambi loggati</div></div>
        <div class="stat-card"><div class="v">${s.today_calls}</div><div class="l">Chiamate oggi</div></div>
        <div class="stat-card"><div class="v">$${s.today_cost_usd.toFixed(4)}</div><div class="l">Costo oggi</div></div>
      </div>
      <div class="stats-chart">
        <div class="ch-title">COSTO PER GIORNO (ultimi ${s.history.length})</div>
        <div class="ch-bars">${barsHtml || '<div style="color:rgba(139, 164, 255,0.4);font-size:11px">Nessun dato</div>'}</div>
        <div class="ch-axis">${axisHtml}</div>
      </div>
    `;
  } catch (e) {
    body.innerHTML = "Errore caricamento statistiche";
  }
}
$("stats-btn").addEventListener("click", async () => {
  openModal("stats-modal");
  await loadStats();
});

// ============================================================
// PC MONITOR DASHBOARD
// ============================================================
let _pcmonInterval = null;

async function loadPcMon() {
  const body = $("pcmon-body");
  try {
    const r = await fetch("/api/pc_stats");
    const s = await r.json();

    const cpuBars = (s.cpu_per_core || []).map((p, i) => `
      <div class="pc-core" title="Core ${i}: ${p.toFixed(0)}%">
        <div class="pc-core-fill" style="height:${p}%"></div>
        <div class="pc-core-label">${p.toFixed(0)}</div>
      </div>
    `).join("");

    const disksHtml = (s.disks || []).map(d => `
      <div class="pc-disk">
        <div class="pc-disk-label">${escapeHtml(d.mount)} <span class="pc-disk-fs">(${escapeHtml(d.fs)})</span></div>
        <div class="pc-bar"><div class="pc-bar-fill" style="width:${d.percent}%"></div></div>
        <div class="pc-disk-detail">${d.used_gb} / ${d.total_gb} GB · ${d.percent}%</div>
      </div>
    `).join("");

    const procsHtml = (s.top_processes || []).map(p => `
      <div class="pc-proc">
        <span class="pc-proc-name">${escapeHtml(p.name)}</span>
        <span class="pc-proc-cpu">${p.cpu.toFixed(0)}% CPU</span>
        <span class="pc-proc-mem">${p.mem}% RAM</span>
      </div>
    `).join("");

    const battery = s.battery ? `
      <div class="pc-section">
        <div class="pc-h">BATTERIA</div>
        <div class="pc-row">
          <div class="pc-bar"><div class="pc-bar-fill" style="width:${s.battery.percent}%; background: ${s.battery.percent > 30 ? 'var(--green)' : 'var(--red)'}"></div></div>
          <div class="pc-stat-val">${s.battery.percent}%</div>
          <div class="pc-stat-sub">${s.battery.plugged ? '⚡ in carica' : '🔋 a batteria'}</div>
        </div>
      </div>
    ` : "";

    body.innerHTML = `
      <div class="pc-grid">
        <div class="pc-section">
          <div class="pc-h">SISTEMA</div>
          <div class="pc-info">${escapeHtml(s.system)} · ${escapeHtml(s.machine)}</div>
          <div class="pc-info-sub">${escapeHtml(s.processor || '')}</div>
          <div class="pc-info-sub">${s.cpu_count} thread (${s.cpu_physical} core fisici) · ${s.cpu_freq_mhz} MHz</div>
          <div class="pc-info-sub">Uptime: ${s.uptime_str}</div>
        </div>

        <div class="pc-section">
          <div class="pc-h">CPU <span class="pc-h-val">${s.cpu_overall}%</span></div>
          <div class="pc-cores">${cpuBars}</div>
        </div>

        <div class="pc-section">
          <div class="pc-h">MEMORIA</div>
          <div class="pc-row">
            <div class="pc-bar"><div class="pc-bar-fill" style="width:${s.memory.percent}%"></div></div>
            <div class="pc-stat-val">${s.memory.used_gb} / ${s.memory.total_gb} GB</div>
            <div class="pc-stat-sub">${s.memory.percent}% · ${s.memory.available_gb} GB liberi</div>
          </div>
          ${s.swap.total_gb > 0 ? `
            <div class="pc-row" style="margin-top:6px">
              <div class="pc-info-sub">SWAP: ${s.swap.used_gb} / ${s.swap.total_gb} GB (${s.swap.percent}%)</div>
            </div>
          ` : ""}
        </div>

        <div class="pc-section">
          <div class="pc-h">DISCHI</div>
          ${disksHtml}
        </div>

        ${battery}

        <div class="pc-section">
          <div class="pc-h">RETE</div>
          <div class="pc-info-sub">↑ ${(s.network.bytes_sent / 1e6).toFixed(1)} MB inviati · ↓ ${(s.network.bytes_recv / 1e6).toFixed(1)} MB ricevuti</div>
          <div class="pc-info-sub">${s.network.packets_sent} pacchetti out · ${s.network.packets_recv} in</div>
        </div>

        <div class="pc-section pc-section-wide">
          <div class="pc-h">TOP PROCESSI</div>
          ${procsHtml}
        </div>
      </div>
    `;
  } catch (e) {
    body.innerHTML = "Errore caricamento statistiche PC";
  }
}

// ============================================================
// DIAGNOSTIC + HELP + SEARCH
// ============================================================
const CHECK_LABELS = {
  anthropic_key: "API Anthropic",
  gmail: "Account Gmail",
  whisper: "Modello Whisper (vocale)",
  wake_word: "Wake word ('Hey Vega')",
  microphone: "Microfono",
  internet: "Connessione internet",
  disk_space: "Spazio disco",
  tools: "Tool caricati",
  engine: "Engine Vega",
  memory_file: "File memoria",
};

async function loadDiagnostic() {
  const body = $("diag-body");
  body.innerHTML = "Eseguo controlli...";
  try {
    const r = await fetch("/api/diagnose");
    const d = await r.json();
    const overall = d.overall === "ok"
      ? '<div class="diag-overall ok">✅ Tutti i sistemi operativi</div>'
      : '<div class="diag-overall warn">⚠️ Alcuni controlli da verificare</div>';
    const rows = Object.entries(d.checks || {}).map(([k, v]) => {
      const lbl = CHECK_LABELS[k] || k;
      const icon = v.status === "ok" ? "✅" : (v.status === "warnings" ? "⚠️" : "❌");
      const detail = Object.entries(v).filter(([key]) => key !== "status").map(([key, val]) => `${key}: ${val}`).join(" | ");
      return `<div class="diag-row"><span>${icon} ${lbl}</span><span class="diag-detail">${escapeHtml(v.status)} ${detail ? "· " + escapeHtml(detail) : ""}</span></div>`;
    }).join("");
    const logsR = await fetch("/api/logs");
    const logs = await logsR.json();
    const logTail = (logs.lines || []).slice(-15).join("\n");

    body.innerHTML = `
      ${overall}
      <div class="diag-rows">${rows}</div>
      <div class="diag-section">
        <div class="diag-h">ULTIMI LOG (${(logs.size/1024).toFixed(1)} KB)</div>
        <pre class="diag-log">${escapeHtml(logTail) || "(vuoto)"}</pre>
        <button class="modal-action" id="logs-clear-btn">SVUOTA LOG</button>
      </div>
    `;
    const btn = document.getElementById("logs-clear-btn");
    if (btn) btn.addEventListener("click", async () => {
      await fetch("/api/logs", { method: "DELETE" });
      loadDiagnostic();
    });
  } catch (e) {
    body.innerHTML = "Errore: " + e.message;
  }
}

$("diag-btn").addEventListener("click", () => {
  openModal("diag-modal");
  loadDiagnostic();
});

async function loadHelp() {
  const body = $("help-body");
  body.innerHTML = "Caricamento...";
  try {
    const r = await fetch("/api/help");
    const d = await r.json();
    const sections = Object.entries(d.categories || {}).map(([cat, items]) => {
      const itemsHtml = items.map(it => `
        <div class="help-tool">
          <div class="help-tool-name">${escapeHtml(it.name)}</div>
          <div class="help-tool-desc">${escapeHtml(it.description)}</div>
          ${it.examples ? `<div class="help-tool-ex">${it.examples.map(e => `<span class="help-ex">${escapeHtml(e)}</span>`).join("")}</div>` : ""}
        </div>
      `).join("");
      return `
        <div class="help-cat">
          <div class="help-cat-title">${escapeHtml(cat)} <span style="opacity:0.5">(${items.length})</span></div>
          <div class="help-cat-items">${itemsHtml}</div>
        </div>
      `;
    }).join("");
    body.innerHTML = `
      <div class="help-intro">
        ${d.tool_count} strumenti disponibili. Parla, scrivi, oppure clicca un comando per copiarlo.
      </div>
      <input type="text" id="help-search" placeholder="Filtra comandi..." style="width:100%;background:rgba(139, 164, 255,0.06);border:1px solid var(--cyan-soft);color:var(--cyan);padding:8px 12px;border-radius:4px;outline:none;font-size:13px;margin-bottom:14px;">
      <div id="help-cats">${sections}</div>
    `;
    // filter
    const inp = document.getElementById("help-search");
    if (inp) inp.addEventListener("input", () => {
      const q = inp.value.toLowerCase();
      document.querySelectorAll(".help-tool").forEach(t => {
        const txt = t.textContent.toLowerCase();
        t.style.display = (!q || txt.includes(q)) ? "" : "none";
      });
    });
  } catch (e) {
    body.innerHTML = "Errore: " + e.message;
  }
}

$("help-btn").addEventListener("click", () => {
  openModal("help-modal");
  loadHelp();
});

// Search globale
const _searchInput = document.getElementById("search-input");
async function doGlobalSearch(q) {
  const body = $("search-results");
  if (!q || q.length < 2) {
    body.innerHTML = '<div style="color:rgba(139, 164, 255,0.4);font-size:12px;">Inserisci almeno 2 caratteri</div>';
    return;
  }
  try {
    const r = await fetch("/api/search?q=" + encodeURIComponent(q));
    const d = await r.json();
    if (!d.results || !d.results.length) {
      body.innerHTML = '<div style="color:rgba(139, 164, 255,0.4);font-size:12px;">Nessun risultato</div>';
      return;
    }
    body.innerHTML = d.results.map(res => `
      <div class="search-result">
        <div class="search-cat">${escapeHtml(res.category)}</div>
        <div class="search-text">${escapeHtml(res.text)}</div>
        ${res.timestamp ? `<div class="search-ts">${escapeHtml(res.timestamp)}</div>` : ""}
      </div>
    `).join("");
  } catch (e) {
    body.innerHTML = "Errore: " + e.message;
  }
}
if (_searchInput) {
  let searchTimer = null;
  _searchInput.addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => doGlobalSearch(e.target.value), 300);
  });
}

// Hotkey: Ctrl+K opens search
document.addEventListener("keydown", (e) => {
  if (e.ctrlKey && e.key.toLowerCase() === "k") {
    e.preventDefault();
    openModal("search-modal");
    setTimeout(() => document.getElementById("search-input").focus(), 100);
  }
});

$("pcmon-btn").addEventListener("click", async () => {
  openModal("pcmon-modal");
  await loadPcMon();
  // Live update every 2 seconds while open
  if (_pcmonInterval) clearInterval(_pcmonInterval);
  _pcmonInterval = setInterval(() => {
    const m = document.getElementById("pcmon-modal");
    if (m && m.classList.contains("show")) {
      loadPcMon();
    } else {
      clearInterval(_pcmonInterval);
      _pcmonInterval = null;
    }
  }, 2000);
});

// F11 also toggles fullscreen (browser default, but make sure F nothing weird)
document.addEventListener("keydown", (e) => {
  if (e.key === "F11") {
    e.preventDefault();
    $("fs-btn").click();
  }
});

$("shutdown-btn").addEventListener("click", () => {
  if (!confirm("Spegnere Vega completamente?")) return;
  fetch("/api/shutdown", { method: "POST" });
  setTimeout(() => {
    document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-size:32px;letter-spacing:1em;color:#8ba4ff;">OFFLINE</div>';
  }, 500);
});

// Restart button: kills server, spawns new one, browser reconnects automatically
const restartBtn = document.getElementById("restart-btn");
if (restartBtn) {
  restartBtn.addEventListener("click", () => {
    if (!confirm("Riavviare Vega? Le conversazioni e i modelli vengono ricaricati.")) return;
    restartBtn.classList.add("spinning");
    // Update label without destroying the SVG icon
    const labelSpan = restartBtn.querySelector("span");
    if (labelSpan) labelSpan.textContent = "RIAVVIO";
    fetch("/api/restart", { method: "POST" }).catch(() => {});
    // Wait for server to come back, then reload the page
    let attempts = 0;
    const check = setInterval(async () => {
      attempts++;
      try {
        const r = await fetch("/api/state", { cache: "no-store" });
        if (r.ok) {
          clearInterval(check);
          location.reload();
        }
      } catch (e) {}
      if (attempts > 60) {  // 60s timeout
        clearInterval(check);
        location.reload();
      }
    }, 1000);
  });
}

// ============================================================
// VEGA PAUSE TOGGLE
// ============================================================
let vegaActive = true;
function updatePauseButton() {
  const btn = $("pause-btn");
  if (vegaActive) {
    btn.classList.remove("paused");
    btn.textContent = "🎧 PAUSA";
    btn.title = "Pausa ascolto Vega (per ascoltare musica indisturbato)";
  } else {
    btn.classList.add("paused");
    btn.textContent = "🔇 IN PAUSA";
    btn.title = "Riprendi ascolto Vega";
  }
}
$("pause-btn").addEventListener("click", () => {
  fetch("/api/listen/toggle", { method: "POST" })
    .then(r => r.json())
    .then(d => { vegaActive = !!d.active; updatePauseButton(); });
});

// ============================================================
// BOOT AUDIO (intro Clash - 7s) - uses the SAME player element
// so user can pause/play/stop it with the player controls
// ============================================================
const BOOT_TRACK = {
  name: "The Clash - Should I Stay or Should I Go",
  filename: "__intro__",
  url: "/assets/startup.mp3",
  isIntro: true,
};
let bootMusicEnabled = true;
let isPlayingIntro = false;

function playBootMusic() {
  if (!bootMusicEnabled) return;
  if (isPlayingIntro && !audio.paused) return;

  // Make the Clash behave like a normal library track so play/pause work.
  // The Clash is pinned at index 0 if library is loaded; if not yet, use a virtual track.
  const idx = library.findIndex(t => t.filename === "__intro__");
  isPlayingIntro = true;
  if (idx >= 0) {
    currentIdx = idx;
  }
  audio.src = BOOT_TRACK.url;
  let vol = Number($("pc-vol").value) / 100;
  if (vol < 0.3) vol = 0.55;
  audio.volume = vol;
  $("pc-vol").value = Math.round(vol * 100);
  $("np-title").textContent = BOOT_TRACK.name;
  $("np-artist").textContent = "in riproduzione";
  $("pc-play").textContent = "⏸";
  renderPlaylist();
  const promise = audio.play();
  if (promise && promise.then) {
    promise.catch(() => {
      $("np-title").textContent = "🔇 Click qualsiasi punto per attivare audio";
      $("np-artist").textContent = "audio bloccato dal browser";
      showToast("Audio bloccato - clicca per sbloccare");
    });
  }
}

function stopBootMusic() {
  // Mark that the "intro period" has ended, but DON'T forcibly stop the audio.
  // The user might want to keep listening. We just clear the intro flag so
  // play/pause works normally via library track index.
  isPlayingIntro = false;
}

// ============================================================
// MUSIC PLAYER
// ============================================================
const audio = $("player-audio");
let library = [];          // [{filename, name, url, size}]
let playlistOrder = [];    // indices into library
let currentIdx = -1;
let shuffle = false;
let repeat = false;
let userIsSeeking = false;

function formatTime(s) {
  if (!isFinite(s)) return "0:00";
  s = Math.max(0, Math.floor(s));
  const m = Math.floor(s / 60);
  const ss = s % 60;
  return `${m}:${String(ss).padStart(2, "0")}`;
}

let librarySearch = "";

function formatDur(s) {
  if (!s || !isFinite(s)) return "";
  s = Math.floor(s);
  const m = Math.floor(s / 60);
  const ss = s % 60;
  return `${m}:${String(ss).padStart(2, "0")}`;
}

function renderPlaylist() {
  const pl = $("playlist");
  const countEl = $("pl-count");
  if (!library.length) {
    pl.innerHTML = '<div class="pl-empty">Carica i tuoi MP3 con i tasti qui sopra</div>';
    if (countEl) countEl.textContent = "0 brani";
    return;
  }
  const q = librarySearch.toLowerCase();
  const filtered = library.filter(t => !q || t.name.toLowerCase().includes(q));
  if (countEl) countEl.textContent = `${filtered.length}/${library.length} brani`;
  pl.innerHTML = "";
  if (!filtered.length) {
    pl.innerHTML = '<div class="pl-empty">Nessun risultato</div>';
    return;
  }
  filtered.forEach((track) => {
    const i = library.indexOf(track);
    const div = document.createElement("div");
    div.className = "pl-item" + (i === currentIdx ? " playing" : "") + (track.pinned ? " pinned" : "");
    const dur = track.duration ? formatDur(track.duration) : "";
    const delHtml = track.pinned ? "" : `<span class="pl-del" title="Rimuovi">×</span>`;
    div.innerHTML = `<span class="pl-title">${track.name}</span><span class="pl-duration">${dur}</span>${delHtml}`;
    div.querySelector(".pl-title").addEventListener("click", () => {
      // If clicking the currently playing track, toggle pause/play instead of restarting
      if (i === currentIdx && audio.src) {
        togglePlay();
      } else {
        playIndex(i);
      }
    });
    const delEl = div.querySelector(".pl-del");
    if (delEl) {
      delEl.addEventListener("click", (e) => {
        e.stopPropagation();
        if (!confirm(`Eliminare "${track.name}" dalla libreria?`)) return;
        fetch("/api/music/delete", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({filename: track.filename}),
        }).then(loadLibrary);
      });
    }
    pl.appendChild(div);

    if (track.duration === undefined) {
      const probe = new Audio();
      probe.preload = "metadata";
      probe.src = track.url;
      probe.addEventListener("loadedmetadata", () => {
        track.duration = probe.duration;
        const td = div.querySelector(".pl-duration");
        if (td) td.textContent = formatDur(track.duration);
      }, { once: true });
    }
  });
}

function buildOrder() {
  playlistOrder = library.map((_, i) => i);
  if (shuffle) {
    for (let i = playlistOrder.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [playlistOrder[i], playlistOrder[j]] = [playlistOrder[j], playlistOrder[i]];
    }
  }
}

function playIndex(i) {
  if (i < 0 || i >= library.length) return;
  currentIdx = i;
  const t = library[i];
  audio.src = t.url;
  audio.play().then(() => {
    // When the player starts, auto-pause Vega to avoid feedback (mic picking up music)
    if (vegaActive) {
      fetch("/api/listen/pause", { method: "POST" });
      wasVegaAutoPaused = true;
    }
  }).catch(err => {
    showToast("Click sul play (il browser blocca audio automatico)");
  });
  $("np-title").textContent = t.name;
  $("np-artist").textContent = "in riproduzione";
  $("pc-play").textContent = "⏸";
  renderPlaylist();
}

let wasVegaAutoPaused = false;

function playNext() {
  if (!library.length) return;
  if (!playlistOrder.length) buildOrder();
  const cur = playlistOrder.indexOf(currentIdx);
  let next = cur + 1;
  if (next >= playlistOrder.length) {
    if (repeat) next = 0;
    else { stopPlayer(); return; }
  }
  playIndex(playlistOrder[next]);
}

function playPrev() {
  if (!library.length) return;
  if (audio.currentTime > 3) { audio.currentTime = 0; return; }
  if (!playlistOrder.length) buildOrder();
  const cur = playlistOrder.indexOf(currentIdx);
  let prev = cur - 1;
  if (prev < 0) prev = playlistOrder.length - 1;
  playIndex(playlistOrder[prev]);
}

function togglePlay() {
  // Unified play/pause: if audio has a src, toggle pause. Otherwise start something.
  if (audio.src) {
    if (audio.paused) {
      audio.play().catch(() => {});
      $("pc-play").textContent = "⏸";
      $("np-artist").textContent = "in riproduzione";
    } else {
      audio.pause();
      $("pc-play").textContent = "▶";
      $("np-artist").textContent = "in pausa";
    }
    return;
  }
  // No src yet: pick first track or boot music
  if (library.length) {
    if (!playlistOrder.length) buildOrder();
    playIndex(playlistOrder[0]);
  } else if (bootMusicEnabled) {
    playBootMusic();
  } else {
    showToast("Carica brani con + FILE o + CARTELLA");
  }
}

function stopPlayer() {
  isPlayingIntro = false;
  audio.pause();
  audio.currentTime = 0;
  currentIdx = -1;
  $("pc-play").textContent = "▶";
  $("np-title").textContent = "Stop";
  $("np-artist").textContent = "in attesa";
  renderPlaylist();
  if (wasVegaAutoPaused) {
    fetch("/api/listen/resume", { method: "POST" });
    wasVegaAutoPaused = false;
  }
}

// Play a streaming URL (radio) directly in the player
function playStreamUrl(url, label) {
  try { audio.pause(); audio.currentTime = 0; } catch (e) {}
  isPlayingIntro = false;
  currentIdx = -1;
  audio.src = url;
  audio.volume = Math.max(0.5, Number($("pc-vol").value) / 100);
  $("np-title").textContent = "📻 " + (label || "Radio");
  $("np-artist").textContent = "streaming live";
  $("pc-play").textContent = "⏸";
  audio.play().catch(() => {
    showToast("Streaming radio non raggiungibile");
  });
}

async function loadLibrary() {
  try {
    const r = await fetch("/api/music/library");
    const d = await r.json();
    library = d.items || [];
    buildOrder();
    // If boot music is playing and library now contains the Clash, link currentIdx
    if (isPlayingIntro && currentIdx < 0) {
      const idx = library.findIndex(t => t.filename === "__intro__");
      if (idx >= 0) currentIdx = idx;
    }
    renderPlaylist();
  } catch (e) {}
}

async function uploadFiles(fileList) {
  if (!fileList || !fileList.length) return;
  const fd = new FormData();
  let count = 0;
  for (const f of fileList) {
    if (f.type.startsWith("audio/") || /\.(mp3|wav|m4a|ogg|flac)$/i.test(f.name)) {
      fd.append("files", f);
      count++;
    }
  }
  if (!count) {
    showToast("Nessun file audio valido");
    return;
  }
  showToast(`Carico ${count} brani...`);
  try {
    const r = await fetch("/api/music/upload", {method: "POST", body: fd});
    const d = await r.json();
    showToast(`Caricati ${d.saved.length} brani`);
    await loadLibrary();
  } catch (e) {
    showToast("Errore upload");
  }
}

$("pc-play").addEventListener("click", togglePlay);
$("pc-next").addEventListener("click", playNext);
$("pc-prev").addEventListener("click", playPrev);
$("pc-stop").addEventListener("click", stopPlayer);
$("pc-shuffle").addEventListener("click", () => {
  shuffle = !shuffle;
  $("pc-shuffle").classList.toggle("active", shuffle);
  buildOrder();
  localStorage.setItem("vega_player_shuffle", shuffle ? "1" : "0");
});
$("pc-repeat").addEventListener("click", () => {
  repeat = !repeat;
  $("pc-repeat").classList.toggle("active", repeat);
  localStorage.setItem("vega_player_repeat", repeat ? "1" : "0");
});
$("pc-vol").addEventListener("input", (e) => {
  audio.volume = e.target.value / 100;
  localStorage.setItem("vega_player_vol", e.target.value);
});

// Restore volume from last session
const savedVol = localStorage.getItem("vega_player_vol");
if (savedVol !== null) {
  $("pc-vol").value = savedVol;
  audio.volume = Number(savedVol) / 100;
} else {
  audio.volume = 0.8;
}

// Restore shuffle/repeat preferences
if (localStorage.getItem("vega_player_shuffle") === "1") {
  shuffle = true;
  $("pc-shuffle").classList.add("active");
}
if (localStorage.getItem("vega_player_repeat") === "1") {
  repeat = true;
  $("pc-repeat").classList.add("active");
}

audio.addEventListener("ended", () => {
  isPlayingIntro = false;
  if (repeat && playlistOrder.length === 1) {
    audio.currentTime = 0;
    audio.play().catch(() => {});
    return;
  }
  const cur = playlistOrder.indexOf(currentIdx);
  if (cur >= 0 && cur + 1 < playlistOrder.length) {
    playNext();
  } else if (repeat) {
    playNext();
  } else {
    stopPlayer();
  }
});

audio.addEventListener("pause", () => {
  $("pc-play").textContent = "▶";
  if (audio.currentTime > 0 && wasVegaAutoPaused && audio.ended === false) {
    fetch("/api/listen/resume", { method: "POST" });
    wasVegaAutoPaused = false;
  }
});

audio.addEventListener("play", () => {
  $("pc-play").textContent = "⏸";
});

audio.addEventListener("timeupdate", () => {
  if (userIsSeeking) return;
  const cur = audio.currentTime;
  const dur = audio.duration || 0;
  if (dur > 0) {
    $("seek-fill").style.width = ((cur / dur) * 100) + "%";
  }
  $("cur-time").textContent = formatTime(cur);
  $("dur-time").textContent = formatTime(dur);
});

$("seek-bar").addEventListener("click", (e) => {
  const rect = $("seek-bar").getBoundingClientRect();
  const pct = (e.clientX - rect.left) / rect.width;
  if (audio.duration) audio.currentTime = pct * audio.duration;
});

// File / folder add
$("player-mini").addEventListener("click", () => $("file-add").click());
$("add-files").addEventListener("click", () => $("file-add").click());
$("add-folder").addEventListener("click", () => $("folder-add").click());

$("file-add").addEventListener("change", (e) => uploadFiles(e.target.files));
$("folder-add").addEventListener("change", (e) => uploadFiles(e.target.files));

// ============================================================
// DRAG & DROP: trascini un file sulla finestra
//   - audio (mp3, wav, m4a...)  -> aggiunto alla libreria musica
//   - PDF, txt, md, csv         -> Vega lo analizza/riassume
//   - immagini                  -> Vega le riceve
// ============================================================
let _dropOverlay = null;
function ensureDropOverlay() {
  if (_dropOverlay) return _dropOverlay;
  _dropOverlay = document.createElement("div");
  _dropOverlay.className = "drop-overlay";
  _dropOverlay.innerHTML = `
    <div class="drop-inner">
      <div class="drop-icon">⬇</div>
      <div class="drop-text">RILASCIA PER ANALIZZARE</div>
      <div class="drop-sub">PDF · TXT · MD · MP3 · immagini</div>
    </div>
  `;
  document.body.appendChild(_dropOverlay);
  return _dropOverlay;
}

let _dragCounter = 0;
window.addEventListener("dragenter", (e) => {
  e.preventDefault();
  _dragCounter++;
  ensureDropOverlay().classList.add("show");
});
window.addEventListener("dragleave", (e) => {
  _dragCounter--;
  if (_dragCounter <= 0) {
    _dragCounter = 0;
    if (_dropOverlay) _dropOverlay.classList.remove("show");
  }
});
window.addEventListener("dragover", (e) => { e.preventDefault(); });
window.addEventListener("drop", async (e) => {
  e.preventDefault();
  _dragCounter = 0;
  if (_dropOverlay) _dropOverlay.classList.remove("show");
  if (!e.dataTransfer || !e.dataTransfer.files || !e.dataTransfer.files.length) return;

  const files = Array.from(e.dataTransfer.files);
  for (const f of files) {
    const name = f.name.toLowerCase();
    const isAudio = /\.(mp3|wav|m4a|ogg|flac)$/.test(name) || (f.type && f.type.startsWith("audio/"));
    if (isAudio) {
      // Music library upload
      await uploadFiles([f]);
    } else {
      // Send to analyze endpoint
      const fd = new FormData();
      fd.append("file", f);
      showToast(`Analizzo ${f.name}...`);
      try {
        await fetch("/api/analyze_file", { method: "POST", body: fd });
      } catch (err) {
        showToast("Errore analisi file");
      }
    }
  }
});

// Library search box
const searchInput = document.getElementById("pl-search");
if (searchInput) {
  searchInput.addEventListener("input", (e) => {
    librarySearch = e.target.value;
    renderPlaylist();
  });
}

// Keyboard shortcuts (only when NOT typing in input)
document.addEventListener("keydown", (e) => {
  const inInput = ["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName);
  if (inInput) return;

  // Space = play/pause player
  if (e.code === "Space") { e.preventDefault(); togglePlay(); return; }
  // Arrow Right = next, Left = prev
  if (e.code === "ArrowRight") { e.preventDefault(); playNext(); return; }
  if (e.code === "ArrowLeft") { e.preventDefault(); playPrev(); return; }
  // Arrow Up / Down = volume
  if (e.code === "ArrowUp") {
    e.preventDefault();
    const v = Math.min(100, Number($("pc-vol").value) + 5);
    $("pc-vol").value = v;
    audio.volume = v / 100;
    localStorage.setItem("vega_player_vol", String(v));
    return;
  }
  if (e.code === "ArrowDown") {
    e.preventDefault();
    const v = Math.max(0, Number($("pc-vol").value) - 5);
    $("pc-vol").value = v;
    audio.volume = v / 100;
    localStorage.setItem("vega_player_vol", String(v));
    return;
  }
  // M = toggle Vega pause (mute listening)
  if (e.key === "m" || e.key === "M") {
    e.preventDefault();
    $("pause-btn").click();
    return;
  }
  // J = wake Vega manually
  if (e.key === "j" || e.key === "J") {
    e.preventDefault();
    $("wake-btn").click();
    return;
  }
  // S = stop Vega voice
  if (e.key === "s" || e.key === "S") {
    e.preventDefault();
    $("stop-btn").click();
    return;
  }
});

// Initial library load
loadLibrary();

// ============================================================
// Boot music: start after slight delay so audio context is ready
// ============================================================
setTimeout(() => { playBootMusic(); }, 800);
// Don't force-stop at 7.5s anymore. The engine sends an explicit
// "music stop" WS event before speaking the greeting. After that the
// audio can still be controlled freely via player buttons.

// Audio context unlock: ONCE on first user gesture only.
// Critical: this MUST be {once: true} otherwise every click in the app
// would re-trigger boot music (causing buttons to "restart the song").
let _audioContextUnlocked = false;
function unlockAudio() {
  if (_audioContextUnlocked) return;
  _audioContextUnlocked = true;
  // Wake up audio context for synthesized beeps
  if (_audioCtx && _audioCtx.state === "suspended") {
    _audioCtx.resume();
  }
  // If boot music was blocked by autoplay AND never played, try once
  if (audio.paused && bootMusicEnabled && audio.src
      && audio.src.includes("startup.mp3") && audio.currentTime === 0) {
    isPlayingIntro = true;
    audio.volume = Math.max(0.55, Number($("pc-vol").value) / 100);
    audio.play().catch(() => {});
  }
}
window.addEventListener("click", unlockAudio, { once: true });
window.addEventListener("keydown", unlockAudio, { once: true });


// ============ Mic privacy HUD ============
function _updateMicHud(state) {
  const hud = $("mic-hud");
  if (!hud) return;
  hud.classList.remove("mic-off", "mic-listening", "mic-speaking");
  let label = "MIC OFF";
  if (state === "listening" || state === "wake_listening") {
    hud.classList.add("mic-listening");
    label = "MIC ON · ASCOLTO";
  } else if (state === "speaking") {
    hud.classList.add("mic-speaking");
    label = "VEGA PARLA";
  } else if (state === "thinking") {
    hud.classList.add("mic-speaking");
    label = "ELABORA";
  } else {
    hud.classList.add("mic-off");
    label = "MIC OFF";
  }
  const lbl = hud.querySelector(".mic-label");
  if (lbl) lbl.textContent = label;
}

// Click to toggle global pause (kill switch)
(function _wireMicHud() {
  const hud = document.getElementById("mic-hud");
  if (!hud) return;
  hud.addEventListener("click", async () => {
    try {
      await fetch("/api/listen/pause", { method: "POST" });
      _updateMicHud("idle");
      showToast("Microfono in pausa");
    } catch (e) {}
  });
})();


// ============ Push notifications (PWA mobile) ============
async function _registerPushIfMobile() {
  // Only attempt on mobile / when SW is supported
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
  try {
    const reg = await navigator.serviceWorker.ready;
    const existing = await reg.pushManager.getSubscription();
    if (existing) return; // already subscribed
    const r = await fetch("/api/push/public_key");
    const j = await r.json();
    if (!j.public_key) return;
    // Convert URL-safe base64 → Uint8Array
    const pad = "=".repeat((4 - j.public_key.length % 4) % 4);
    const b64 = (j.public_key + pad).replace(/-/g, "+").replace(/_/g, "/");
    const raw = atob(b64);
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: bytes,
    });
    await fetch("/api/push/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(sub),
    });
    console.log("[push] subscribed");
  } catch (e) {
    console.warn("[push] subscribe failed:", e);
  }
}
// Trigger after user interaction (permission prompt requires gesture on iOS)
window.addEventListener("click", () => _registerPushIfMobile(), { once: true });


// ============ Agent progress card (multi-step agent_fabric) ============
const _agentRuns = {};  // run_id -> {goal, plan: [], steps: {id:status}, cardEl}

function handleAgentProgress(p) {
  if (!p || !p.run_id) return;
  let run = _agentRuns[p.run_id];
  if (!run) {
    run = { goal: p.goal || "", plan: [], steps: {}, summary: "", cardEl: null };
    _agentRuns[p.run_id] = run;
    run.cardEl = _createAgentCard(p.run_id, run);
  }
  const kind = p.kind;
  const data = p.data || {};
  if (kind === "plan") {
    run.plan = (data.plan || []).map(s => ({ id: s.id, action: s.action, agent: s.agent, status: "pending" }));
    _renderAgentCard(p.run_id);
  } else if (kind === "executing") {
    if (run.steps[data.id] !== "done") run.steps[data.id] = "running";
    const step = run.plan.find(s => s.id === data.id);
    if (step) step.status = "running";
    _renderAgentCard(p.run_id);
  } else if (kind === "step_done") {
    const step = run.plan.find(s => s.id === data.id);
    if (step) {
      step.status = data.ok ? "done" : "fail";
      step.output = data.output;
      step.error = data.error;
    }
    _renderAgentCard(p.run_id);
  } else if (kind === "verified") {
    run.verification = data;
    _renderAgentCard(p.run_id);
  } else if (kind === "finished") {
    run.summary = (data && data.summary) || "Completato";
    run.duration = data && data.duration_sec;
    run.finalOk = !!(data && data.ok);
    _renderAgentCard(p.run_id);
  }
}

function _createAgentCard(runId, run) {
  const stream = $("transcript-stream") || document.body;
  const el = document.createElement("div");
  el.className = "card agent-card";
  el.id = "agent-card-" + runId;
  el.innerHTML = `<div class="card-header">🤖 AGENT — <span class="agent-goal"></span></div>
    <div class="agent-steps"></div>
    <div class="agent-summary"></div>`;
  el.style.cssText = "border:1px solid #8ba4ff;padding:12px;margin:10px 0;border-radius:8px;background:rgba(0,40,80,0.15);font-family:monospace;";
  stream.appendChild(el);
  return el;
}

function _renderAgentCard(runId) {
  const run = _agentRuns[runId];
  if (!run || !run.cardEl) return;
  run.cardEl.querySelector(".agent-goal").textContent = run.goal;
  const stepsEl = run.cardEl.querySelector(".agent-steps");
  stepsEl.innerHTML = run.plan.map(s => {
    const icon = s.status === "done" ? "✓" :
                 s.status === "fail" ? "✗" :
                 s.status === "running" ? "⟳" : "○";
    const color = s.status === "done" ? "#7cffa1" :
                  s.status === "fail" ? "#ff6b6b" :
                  s.status === "running" ? "#8ba4ff" : "#888";
    return `<div style="margin:4px 0;color:${color}"><b>${icon}</b> [${s.agent}] ${s.action}</div>`;
  }).join("");
  if (run.summary) {
    const okClass = run.finalOk ? "#7cffa1" : "#ffaa66";
    run.cardEl.querySelector(".agent-summary").innerHTML =
      `<div style="margin-top:10px;padding-top:8px;border-top:1px dashed #555;color:${okClass}">
        ${escapeHtml(run.summary)}
        ${run.duration ? `<div style="opacity:.6;font-size:.85em">${run.duration}s</div>` : ""}
      </div>`;
  }
}

function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, c =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}


// ============ Tool progress (live feedback for slow tools) ============
const _toolProgressEls = {};   // tool name -> DOM element

function _renderToolProgress(p) {
  if (!p || !p.tool) return;
  const tool = p.tool;
  const done = !!p.done;
  // Find the status area (under the J.A.R.V.I.S sphere)
  const host = document.getElementById("state-label") || document.body;
  let el = _toolProgressEls[tool];
  if (done) {
    if (el) {
      el.classList.add("fade-out");
      setTimeout(() => {
        if (el && el.parentNode) el.parentNode.removeChild(el);
        delete _toolProgressEls[tool];
      }, 500);
    }
    return;
  }
  if (!el) {
    el = document.createElement("div");
    el.className = "tool-progress-pill";
    // Insert below state-label
    if (host.parentNode) {
      host.parentNode.insertBefore(el, host.nextSibling);
    } else {
      document.body.appendChild(el);
    }
    _toolProgressEls[tool] = el;
  }
  el.textContent = `⏳ ${p.message || tool}`;
  el.title = `${tool} • ${p.elapsed_sec}s`;
}


// ============ Operations Center (Log / Workflow / TaskQ / Health) ============
window._openOpsCenter = async function() {
  let modal = document.getElementById("ops-modal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "ops-modal";
    modal.className = "modal";
    modal.innerHTML = `
      <div class="modal-box modal-xl">
        <div class="modal-head">
          <span>🛠 OPERATIONS CENTER</span>
          <button class="modal-close" data-close="ops-modal">×</button>
        </div>
        <div class="ops-tabs">
          <button class="ops-tab active" data-ops="health">🏥 HEALTH</button>
          <button class="ops-tab" data-ops="workflow">🔄 WORKFLOW</button>
          <button class="ops-tab" data-ops="queue">📋 TASK QUEUE</button>
          <button class="ops-tab" data-ops="logs">📜 LOG CENTER</button>
          <button class="ops-tab" data-ops="trace">🔍 TRACE</button>
        </div>
        <div class="modal-body ops-body" id="ops-body">Carico...</div>
      </div>`;
    document.body.appendChild(modal);
    modal.querySelector("[data-close]").addEventListener("click",
      () => modal.classList.remove("show"));
    modal.querySelectorAll(".ops-tab").forEach(t => {
      t.addEventListener("click", () => {
        modal.querySelectorAll(".ops-tab").forEach(x => x.classList.remove("active"));
        t.classList.add("active");
        _renderOpsTab(t.getAttribute("data-ops"));
      });
    });
  }
  modal.classList.add("show");
  _renderOpsTab("health");
};

async function _renderOpsTab(name) {
  const body = document.getElementById("ops-body");
  if (!body) return;
  body.innerHTML = '<div style="opacity:.6;padding:20px">Caricamento...</div>';
  try {
    if (name === "health") {
      const r = await (await fetch("/api/health")).json();
      const statusColor = {healthy: "#7cffa1", degraded: "#ffb454", unhealthy: "#ff5b6b"}[r.status] || "#888";
      body.innerHTML = `
        <div style="padding:16px">
          <div style="font-family:var(--font-display);font-size:1.4em;color:${statusColor};letter-spacing:.2em;margin-bottom:12px">
            ${escapeHtml(r.status.toUpperCase())}
          </div>
          <div style="opacity:.7;margin-bottom:16px">Uptime: ${Math.floor(r.uptime_sec/60)} min</div>
          <table class="ops-table">
            <thead><tr><th>Componente</th><th>Stato</th><th>Dettagli</th></tr></thead>
            <tbody>
            ${Object.entries(r.components).map(([k,v]) => `
              <tr>
                <td><b>${escapeHtml(k)}</b></td>
                <td><span class="ops-pill ops-${v.ok === true ? 'ok' : v.ok === false ? 'fail' : 'opt'}">
                  ${v.ok === true ? '✓ OK' : v.ok === false ? '✗ FAIL' : '— opt'}
                </span></td>
                <td>${escapeHtml(v.detail || "")}</td>
              </tr>
            `).join("")}
            </tbody>
          </table>
        </div>`;
    } else if (name === "workflow") {
      const r = await (await fetch("/api/workflows/team/list")).json();
      body.innerHTML = `
        <div style="padding:16px">
          <h3 style="font-family:var(--font-display);color:var(--hud-cyan);letter-spacing:.15em">Workflow disponibili</h3>
          ${(r.workflows||[]).map(w => `
            <div class="ops-card">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <div>
                  <b>${escapeHtml(w.name)}</b>
                  <div style="opacity:.7;font-size:.88em">${escapeHtml(w.description||"")}</div>
                  <div style="opacity:.5;font-size:.8em">Trigger: ${escapeHtml(w.trigger||"manual")} · ${w.steps_count} step</div>
                </div>
                <button class="modal-action" onclick="_runWorkflow('${w.name}')">▶ RUN</button>
              </div>
            </div>
          `).join("")}
          <h3 style="font-family:var(--font-display);color:var(--hud-cyan);letter-spacing:.15em;margin-top:24px">Run recenti</h3>
          ${(r.recent_runs||[]).slice(0,10).map(run => `
            <div class="ops-card">
              <b>${escapeHtml(run.workflow)}</b>
              <span class="ops-pill ops-${run.ok ? 'ok' : 'fail'}">${run.ok ? '✓' : '✗'} ${run.steps_succeeded}/${run.steps_total}</span>
              <span style="opacity:.6;font-size:.85em;margin-left:8px">${run.duration_sec}s · ${new Date(run.started_at*1000).toLocaleString('it-IT')}</span>
            </div>
          `).join("") || '<div style="opacity:.5">Nessuna run ancora</div>'}
        </div>`;
    } else if (name === "queue") {
      const r = await (await fetch("/api/tasks")).json();
      const s = r.stats || {};
      body.innerHTML = `
        <div style="padding:16px">
          <div class="ops-stats-row">
            <div class="ops-stat"><div class="ops-stat-n" style="color:var(--hud-gold)">${s.pending||0}</div><div>PENDING</div></div>
            <div class="ops-stat"><div class="ops-stat-n" style="color:var(--hud-cyan)">${s.running||0}</div><div>RUNNING</div></div>
            <div class="ops-stat"><div class="ops-stat-n" style="color:var(--hud-green)">${s.ok||0}</div><div>OK</div></div>
            <div class="ops-stat"><div class="ops-stat-n" style="color:var(--hud-red)">${s.dlq||0}</div><div>DLQ</div></div>
            <div class="ops-stat"><div class="ops-stat-n">${s.total||0}</div><div>TOT</div></div>
          </div>
          <div style="opacity:.7;margin-top:14px;font-size:.9em">Task queue gestita da SQLite con WAL + retry esponenziale. La Dead Letter Queue contiene task falliti dopo max_attempts.</div>
        </div>`;
    } else if (name === "logs") {
      const audit = await (await fetch("/api/audit/tail?n=50")).json();
      const records = audit.records || [];
      body.innerHTML = `
        <div style="padding:16px">
          <h3 style="font-family:var(--font-display);color:var(--hud-cyan);letter-spacing:.15em">Audit log (ultimi 50)</h3>
          <div class="ops-log-list">
            ${records.slice().reverse().map(r => `
              <div class="ops-log-row">
                <span class="ops-log-time">${new Date(r.ts).toLocaleTimeString('it-IT')}</span>
                <span class="ops-log-event">${escapeHtml(r.event)}</span>
                <span class="ops-log-data">${escapeHtml(JSON.stringify(r.data).slice(0,140))}</span>
              </div>
            `).join("") || '<div style="opacity:.5">Vuoto</div>'}
          </div>
        </div>`;
    } else if (name === "trace") {
      const r = await (await fetch("/api/trace/recent?limit=30")).json();
      body.innerHTML = `
        <div style="padding:16px">
          <h3 style="font-family:var(--font-display);color:var(--hud-cyan);letter-spacing:.15em">Trace recenti</h3>
          ${(r.traces||[]).map(t => `
            <div class="ops-card" style="cursor:pointer" onclick="_showTrace('${t.trace_id}')">
              <span style="font-family:var(--font-mono);color:var(--hud-cyan)">${escapeHtml(t.trace_id)}</span>
              <span style="margin-left:10px;opacity:.7">${escapeHtml(t.first_event)}</span>
              <span style="margin-left:10px;opacity:.5">${t.span_count} span · ${t.duration_ms}ms</span>
              <span style="margin-left:10px;opacity:.5;font-size:.85em">${new Date(t.last_ts).toLocaleTimeString('it-IT')}</span>
            </div>
          `).join("") || '<div style="opacity:.5">Nessun trace recente</div>'}
        </div>`;
    }
  } catch (e) {
    body.innerHTML = `<div style="color:var(--hud-red);padding:16px">Errore: ${escapeHtml(e.message)}</div>`;
  }
}

window._runWorkflow = async function(name) {
  if (!confirm(`Eseguo il workflow "${name}"?`)) return;
  showToast(`Lancio ${name}...`);
  try {
    const r = await fetch("/api/workflows/team/run", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({workflow: name, payload: {}}),
    });
    const j = await r.json();
    showToast(j.ok ? `✓ ${name} OK (${j.steps_succeeded}/${j.steps_total})` : `✗ ${name} fallito`);
    _renderOpsTab("workflow");
  } catch (e) {
    showToast("Errore: " + e.message);
  }
};

window._showTrace = async function(tid) {
  try {
    const r = await (await fetch(`/api/trace/${tid}`)).json();
    const body = document.getElementById("ops-body");
    body.innerHTML = `
      <div style="padding:16px">
        <button class="chat-btn-secondary" onclick="_renderOpsTab('trace')">← indietro</button>
        <h3 style="font-family:var(--font-mono);color:var(--hud-cyan);margin:10px 0">${escapeHtml(tid)}</h3>
        ${(r.spans||[]).map(s => `
          <div class="ops-log-row">
            <span class="ops-log-time">${new Date(s.ts).toLocaleTimeString('it-IT')}</span>
            <span class="ops-log-event">${escapeHtml(s.event)}</span>
            <span class="ops-log-data">${escapeHtml(JSON.stringify(s.data).slice(0,200))}</span>
          </div>
        `).join("")}
      </div>`;
  } catch (e) {
    showToast("Errore: " + e.message);
  }
};


// ============ Theme toggle (dark/light/auto) ============
function applyTheme(mode) {
  const body = document.body;
  body.classList.remove("theme-light", "theme-dark");
  if (mode === "light") {
    body.classList.add("theme-light");
  } else if (mode === "auto") {
    const h = new Date().getHours();
    if (h >= 7 && h < 19) body.classList.add("theme-light");
  }
  localStorage.setItem("vega_theme", mode || "dark");
}

// Apply on load
applyTheme(localStorage.getItem("vega_theme") || "dark");

// Auto re-apply every 30min for "auto" mode
setInterval(() => {
  const mode = localStorage.getItem("vega_theme") || "dark";
  if (mode === "auto") applyTheme("auto");
}, 30 * 60 * 1000);

document.addEventListener("DOMContentLoaded", () => {
  const sel = document.getElementById("set-theme");
  if (sel) {
    sel.value = localStorage.getItem("vega_theme") || "dark";
    sel.addEventListener("change", () => applyTheme(sel.value));
  }
});


// ============ Card history (sessione) ============
const _cardHistory = [];   // {type, data, ts}
const _MAX_HISTORY = 50;

(function _patchShowCard() {
  const orig = window.showCard;
  if (typeof orig !== "function") return;
  window.showCard = function(type, data) {
    try {
      _cardHistory.push({type, data, ts: Date.now()});
      if (_cardHistory.length > _MAX_HISTORY) _cardHistory.shift();
    } catch (e) {}
    return orig.call(this, type, data);
  };
})();

window._openCardHistory = function() {
  let modal = document.getElementById("card-history-modal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "card-history-modal";
    modal.className = "modal";
    modal.innerHTML = `
      <div class="modal-box modal-big">
        <div class="modal-head">
          <span>🗂 STORICO CARD (sessione)</span>
          <button class="modal-close" data-close="card-history-modal">×</button>
        </div>
        <div class="modal-body" id="card-history-body"></div>
      </div>`;
    document.body.appendChild(modal);
    modal.querySelector("[data-close]").addEventListener("click",
      () => modal.classList.remove("show"));
  }
  const body = modal.querySelector("#card-history-body");
  if (!_cardHistory.length) {
    body.innerHTML = '<div style="opacity:.6;text-align:center;padding:30px">Nessuna card in questa sessione</div>';
  } else {
    body.innerHTML = _cardHistory.slice().reverse().map((c, i) => {
      const time = new Date(c.ts).toLocaleTimeString("it-IT");
      const title = c.data && (c.data.title || c.type.toUpperCase()) || c.type;
      return `<div class="ch-item" data-idx="${_cardHistory.length - 1 - i}">
        <div class="ch-meta">${time} · <b>${escapeHtml(c.type)}</b></div>
        <div class="ch-title">${escapeHtml(title)}</div>
      </div>`;
    }).join("");
    body.querySelectorAll(".ch-item").forEach(el => {
      el.addEventListener("click", () => {
        const idx = Number(el.getAttribute("data-idx"));
        const c = _cardHistory[idx];
        if (c) {
          modal.classList.remove("show");
          showCard(c.type, c.data);
        }
      });
    });
  }
  modal.classList.add("show");
};


// ============ Help tabs ============
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".help-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      const target = tab.getAttribute("data-htab");
      document.querySelectorAll(".help-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      document.querySelectorAll(".help-content").forEach(c => {
        c.hidden = c.getAttribute("data-htab") !== target;
      });
    });
  });
});


// ============ Onboarding wizard (first run) ============
let _onbStep = 1;
const _onbTotalSteps = 5;

function _showOnbStep(n) {
  document.querySelectorAll(".onb-step").forEach(el => {
    el.hidden = (Number(el.getAttribute("data-step")) !== n);
  });
  const back = $("onb-back");
  const next = $("onb-next");
  const prog = $("onb-progress");
  if (back) back.hidden = (n === 1);
  if (next) next.textContent = (n === _onbTotalSteps) ? "FINE" : "Avanti";
  if (prog) prog.textContent = `${n} / ${_onbTotalSteps}`;
  _onbStep = n;
}

async function _onbCommit() {
  // Step 2: PIN
  const pin = ($("onb-pin")?.value || "").trim();
  if (pin && pin.length >= 4) {
    try {
      await fetch("/api/pin/set", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({pin}),
      });
    } catch (e) {}
  }
  // Step 3: city
  const city = ($("onb-city")?.value || "").trim();
  if (city) {
    try {
      await fetch("/api/settings", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({home_location: city}),
      });
    } catch (e) {}
  }
  // Mark done
  localStorage.setItem("vega_onb_done", "1");
}

document.addEventListener("DOMContentLoaded", async () => {
  // Trigger onboarding on first visit (no localStorage flag + endpoint says no PIN)
  if (localStorage.getItem("vega_onb_done") === "1") return;
  try {
    const r = await fetch("/api/auth/info");
    const info = await r.json();
    if (info.pin_required) {
      // Already configured by someone, skip onboarding
      localStorage.setItem("vega_onb_done", "1");
      return;
    }
  } catch (e) {}
  // Show onboarding
  setTimeout(() => {
    openModal("onboarding-modal");
    _showOnbStep(1);
  }, 1500);

  // Wire buttons
  const nextBtn = $("onb-next");
  const backBtn = $("onb-back");
  const teamYes = $("onb-team-yes");
  const teamNo = $("onb-team-no");
  if (nextBtn) nextBtn.addEventListener("click", async () => {
    if (_onbStep < _onbTotalSteps) {
      _showOnbStep(_onbStep + 1);
    } else {
      await _onbCommit();
      closeModal("onboarding-modal");
    }
  });
  if (backBtn) backBtn.addEventListener("click", () => {
    if (_onbStep > 1) _showOnbStep(_onbStep - 1);
  });
  if (teamYes) teamYes.addEventListener("click", async () => {
    try {
      await fetch("/api/settings", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({team_mode: true}),
      });
    } catch (e) {}
    _showOnbStep(5);
  });
  if (teamNo) teamNo.addEventListener("click", () => _showOnbStep(5));
});
