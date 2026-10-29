// ComfyUI-RotoTools: Roto Review player. Based on ComfyUI-KM-VideoReview (web/js/videoReviewPlayer.js)
// by Kasun Malinda, https://github.com/KasunMalinda/ComfyUI-KM-VideoReview
// MIT License, Copyright (c) 2026 Kasun Malinda (full text in LICENSE-KM-VideoReview).
// Everything of the original player is kept. RotoTools adds (marked "RotoTools" below):
//   * B = RGBA roto: show it over a background colour (or checkerboard), as the alpha matte, or as is
//   * a download row (roto with alpha as ProRes 4444 .mov, alpha matte as mp4)
//   * a history strip of the shots reviewed in this session; click one to review it again
//
// VideoReviewPlayer — RV-style A/B frame-sequence review player.
// Side-effect-free module: only exports the class (ComfyUI auto-imports every
// .js under WEB_DIRECTORY, so nothing may run at import time).

import { VRColorEngine } from "./roto_review_color.js";

// RotoTools: how an RGBA B is shown, background choices and downloads
const B_VIEWS = [
  ["roto", "Roto", "B = the roto over the background colour"],
  ["alpha", "Alpha", "B = the alpha matte (white = subject)"],
  ["rgba", "As is", "B = the frames as they are"],
];
const BACKGROUNDS = [
  ["#ff0000", "Red"], ["#00b140", "Green"], ["#0047bb", "Blue"],
  ["#000000", "Black"], ["#ffffff", "White"], ["#808080", "Grey"], ["checker", "Checker"],
];
const DOWNLOAD_KINDS = [
  ["roto_alpha", "Roto with alpha (ProRes 4444 .mov)"],
  ["alpha", "Alpha matte (mp4)"],
];
const RR_STYLE_ID = "rr-player-style";
const RR_CSS = `
.rr-bar { display:flex; flex-wrap:wrap; align-items:center; gap:4px 8px; padding:4px 6px; background:#1c1c1c;
  border-top:1px solid #2a2a2a; flex:0 0 auto; font-size:11px; }
.rr-bar label { color:#9a9a9a; }
.rr-bar select { background:#2a2a2a; color:#ccc; border:1px solid #3a3a3a; border-radius:3px; height:22px; }
.rr-bar button { background:#2d5a8a; color:#fff; border:1px solid #4a7fb5; border-radius:3px; height:22px;
  cursor:pointer; padding:0 8px; font-size:11px; }
.rr-bar button:disabled { opacity:.6; cursor:wait; }
.rr-bar .rr-name { flex:1 1 auto; color:#fc3; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; min-width:40px; }
.rr-hist { display:flex; gap:6px; overflow-x:auto; overflow-y:hidden; padding:4px 6px; background:#151515;
  border-top:1px solid #2a2a2a; flex:0 0 auto; min-height:58px; }
.rr-hist .rr-empty { color:#666; font-size:11px; align-self:center; }
.rr-h { flex:0 0 auto; width:84px; cursor:pointer; border:2px solid transparent; border-radius:3px;
  background:#000; position:relative; }
.rr-h:hover { border-color:#58f; }
.rr-h.rr-cur { border-color:#fc3; }
.rr-h img { width:100%; height:44px; object-fit:cover; display:block; }
.rr-h span { position:absolute; left:0; right:0; bottom:0; font-size:10px; background:rgba(0,0,0,.65);
  color:#ddd; padding:0 3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
`;

const MAX_CONCURRENT_LOADS = 8;
const FPS_OPTIONS = [4, 8, 12, 24, 25, 30, 48, 96];
const MODES = [
  ["wipeH", "Wipe H"],
  ["wipeV", "Wipe V"],
  ["side", "Side by Side"],
  ["diff", "Difference"],
  ["abflip", "A/B Flip"],
];

// Loop control cycles through these in order.
const LOOP_MODES = [
  ["once", "→", "Play once (no loop)"],
  ["loop", "↻", "Loop"],
  ["bounce", "⇄", "Bounce (ping-pong)"],
];
const LOOP_TOOLTIP = "Loop mode — Once / Loop / Bounce.";

const STYLE_ID = "vr-player-style";
const CSS = `
.vr-root { display:flex; flex-direction:column; width:100%; height:100%; background:#111;
  color:#ccc; font-family:sans-serif; font-size:12px; outline:none; border-radius:4px; overflow:hidden; }
.vr-root:focus { box-shadow: inset 0 0 0 1px #58f; }
.vr-viewport { position:relative; flex:1 1 auto; min-height:0; }
.vr-canvas { position:absolute; inset:0; width:100%; height:100%; }
.vr-overlay { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center;
  justify-content:center; gap:10px; background:rgba(0,0,0,.55); pointer-events:none; text-align:center; }
.vr-progressbar { width:70%; height:8px; background:#222; border:1px solid #333; border-radius:4px; overflow:hidden; }
.vr-progressbar > div { height:100%; background:#3fb950; width:0%; transition:width .08s linear; }
.vr-flip { position:absolute; top:6px; left:6px; z-index:3; background:rgba(0,0,0,0.6); color:#fff;
  border:1px solid rgba(255,255,255,0.45); border-radius:3px; font-weight:bold; font-size:13px;
  min-width:28px; height:24px; cursor:pointer; pointer-events:auto; }
.vr-flip:hover { background:rgba(40,74,106,0.9); border-color:#58f; }
.vr-info-warn { flex:1 1 auto; text-align:center; color:#e0913f; font-size:11px; }
.vr-controls { display:flex; flex-wrap:wrap; align-items:center; gap:4px 8px;
  min-height:40px; padding:4px 6px; background:#1c1c1c; flex:0 0 auto; }
.vr-group { display:flex; align-items:center; gap:4px; }
.vr-group-scrub { flex:1 1 160px; min-width:120px; }
.vr-controls button { background:#2a2a2a; color:#ccc; border:1px solid #3a3a3a; border-radius:3px;
  height:24px; min-width:26px; cursor:pointer; padding:0 4px; font-size:12px; line-height:1; }
.vr-controls button:hover { background:#383838; }
.vr-controls button.vr-on { background:#2a4a6a; border-color:#58f; color:#fff; }
.vr-controls select { background:#2a2a2a; color:#ccc; border:1px solid #3a3a3a; border-radius:3px; height:24px; }
.vr-scrub { flex:1 1 auto; min-width:40px; height:16px; position:relative; cursor:pointer; }
.vr-scrub-track { position:absolute; left:0; right:0; top:50%; transform:translateY(-50%);
  height:5px; background:#333; border-radius:3px; overflow:hidden; }
.vr-scrub-fill { height:100%; width:0%; background:#58f; }
.vr-scrub-knob { position:absolute; top:50%; left:0%; width:11px; height:11px; margin-left:-5px;
  transform:translateY(-50%); border-radius:50%; background:#fff; box-shadow:0 0 2px #000; pointer-events:none; }
.vr-counter { min-width:64px; text-align:center; font-variant-numeric:tabular-nums; }
.vr-colorbar { display:flex; flex-wrap:wrap; align-items:center; gap:4px 10px;
  padding:4px 8px; background:#1c1c1c; border-top:1px solid #2a2a2a; flex:0 0 auto; font-size:11px; }
.vr-colorbar label { color:#9a9a9a; }
.vr-colorbar input[type=range] { width:90px; height:14px; }
.vr-colorbar .vr-cc-val { min-width:34px; text-align:right; font-variant-numeric:tabular-nums; color:#ccc; }
.vr-colorbar select { background:#2a2a2a; color:#ccc; border:1px solid #3a3a3a; border-radius:3px; height:22px; }
.vr-colorbar button { background:#2a2a2a; color:#ccc; border:1px solid #3a3a3a; border-radius:3px;
  height:22px; min-width:24px; cursor:pointer; font-size:11px; }
.vr-colorbar button:hover { background:#383838; }
.vr-info { flex:0 0 auto; background:#181818; border-top:1px solid #2a2a2a; }
.vr-info-header { display:flex; align-items:center; padding:5px 8px; cursor:pointer; color:#9a9a9a; user-select:none; font-size:11px; }
.vr-info-header:hover { color:#fff; }
.vr-info-body { padding:0 10px 8px; color:#bbb; font-size:11px; line-height:1.6; }
.vr-info-body .vr-k { color:#7fb0ff; }
.vr-info-body .vr-dim { color:#777; }
.vr-root:fullscreen { background:#000; border-radius:0; }
.vr-root:fullscreen .vr-controls { height:56px; padding:0 12px; }
.vr-root:fullscreen .vr-controls button { height:30px; min-width:32px; font-size:14px; }
`;

function ensureStyle() {
  // RotoTools: our extra rows have their own style block
  if (!document.getElementById(RR_STYLE_ID)) {
    const r = document.createElement("style");
    r.id = RR_STYLE_ID;
    r.textContent = RR_CSS;
    document.head.appendChild(r);
  }
  if (document.getElementById(STYLE_ID)) return;
  const s = document.createElement("style");
  s.id = STYLE_ID;
  s.textContent = CSS;
  document.head.appendChild(s);
}

function fitRect(imgW, imgH, boxX, boxY, boxW, boxH) {
  const scale = Math.min(boxW / imgW, boxH / imgH);
  const w = imgW * scale;
  const h = imgH * scale;
  return { x: boxX + (boxW - w) / 2, y: boxY + (boxH - h) / 2, w, h };
}

export class VideoReviewPlayer {
  constructor(node, api) {
    this.node = node;
    this.api = api;
    ensureStyle();

    this.s = {
      generation: 0,
      a: [], // [{url, img|null, status:'pending'|'ok'|'err'}]
      b: [],
      frameCount: 0,
      cur: 0,
      playing: false,
      dir: 1, // travel direction (flips during bounce)
      playDir: 1, // direction the user pressed (stable through bounce)
      loopMode: "loop", // 'once' | 'loop' | 'bounce'
      fps: 24,
      userFps: false, // user touched the fps select; node fps no longer overrides
      mode: "wipeH",
      wipe: 0.5,
      abShow: "a", // which stream A/B Flip mode is showing
      aspect: 9 / 16, // h/w of stream A
      loaded: 0,
      errored: 0,
      total: 0,
      badge: "",
      info: null, // { aW,aH,aCount, bW,bH,bCount }
      cp: { exposure: 0, gamma: 1 }, // interactive exposure/gamma
      // RotoTools
      bAlpha: false, // B carries an alpha channel (the roto)
      bView: "roto", // 'roto' | 'alpha' | 'rgba'
      bg: "#ff0000", // background behind the roto
      runId: null,
      name: "",
      history: [],
    };
    this.engine = null; // VRColorEngine, created lazily
    this.engineFailed = false;
    this.queue = [];
    this.inflight = 0;
    this.raf = 0;
    this.lastTs = 0;
    this.acc = 0;
    this.dragging = false;
    this.scrubbing = false;
    this.infoOpen = false;

    this.#buildDom();
    this.#showMessage("Run workflow to load frames");
    this.ro = new ResizeObserver(() => this.#resizeCanvas());
    this.ro.observe(this.viewportEl);

    // Keep the fullscreen button state and canvas size in sync with fullscreen.
    this.onFsChange = () => {
      this.btnFs.classList.toggle("vr-on", document.fullscreenElement === this.root);
      requestAnimationFrame(() => this.#resizeCanvas());
    };
    document.addEventListener("fullscreenchange", this.onFsChange);
  }

  get rootEl() {
    return this.root;
  }

  get aspect() {
    return this.s.aspect;
  }

  // ------------------------------------------------------------------ DOM

  #buildDom() {
    const root = (this.root = document.createElement("div"));
    root.className = "vr-root";
    root.tabIndex = 0;

    const viewport = (this.viewportEl = document.createElement("div"));
    viewport.className = "vr-viewport";
    const canvas = (this.canvas = document.createElement("canvas"));
    canvas.className = "vr-canvas";
    this.ctx = canvas.getContext("2d");
    viewport.appendChild(canvas);

    // A/B Flip button — an on-screen clickable label (only shown in A/B Flip mode).
    const flipBtn = (this.flipBtn = document.createElement("button"));
    flipBtn.className = "vr-flip";
    flipBtn.textContent = "A";
    flipBtn.title = "Click or press F to flip between A and B";
    flipBtn.style.display = "none";
    flipBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      this.#toggleAB();
      this.root.focus();
    });
    flipBtn.addEventListener("pointerdown", (e) => e.stopPropagation());
    viewport.appendChild(flipBtn);

    const overlay = (this.overlayEl = document.createElement("div"));
    overlay.className = "vr-overlay";
    this.overlayText = document.createElement("div");
    this.progressBar = document.createElement("div");
    this.progressBar.className = "vr-progressbar";
    this.progressFill = document.createElement("div");
    this.progressBar.appendChild(this.progressFill);
    overlay.append(this.overlayText, this.progressBar);
    viewport.appendChild(overlay);

    const controls = document.createElement("div");
    controls.className = "vr-controls";
    // Three groups that each stay intact when the bar wraps to multiple rows:
    // transport buttons · scrubber · mode/options.
    const gTransport = document.createElement("div");
    gTransport.className = "vr-group";
    const gScrub = document.createElement("div");
    gScrub.className = "vr-group vr-group-scrub";
    const gOptions = document.createElement("div");
    gOptions.className = "vr-group";
    controls.append(gTransport, gScrub, gOptions);

    const btn = (parent, label, title, onclick) => {
      const b = document.createElement("button");
      b.textContent = label;
      b.title = title;
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        onclick();
        this.root.focus();
      });
      parent.appendChild(b);
      return b;
    };

    btn(gTransport, "⏮", "First frame (Home)", () => this.seek(0));
    btn(gTransport, "❮", "Step back (←)", () => this.step(-1));
    // Play buttons toggle: click to play in that direction, click again to pause.
    this.btnPlayRev = btn(gTransport, "◀", "Play / pause reverse", () => this.togglePlayDir(-1));
    this.btnPlayFwd = btn(gTransport, "▶", "Play / pause (Space)", () => this.togglePlayDir(1));
    btn(gTransport, "❯", "Step forward (→)", () => this.step(1));
    btn(gTransport, "⏭", "Last frame (End)", () => this.seek(this.s.frameCount - 1));

    // Draggable scrubber (custom, so click AND drag both seek reliably even as a
    // DOM widget over the LiteGraph canvas).
    const scrub = (this.scrubEl = document.createElement("div"));
    scrub.className = "vr-scrub";
    scrub.title = "Drag to scrub";
    const track = document.createElement("div");
    track.className = "vr-scrub-track";
    this.scrubFill = document.createElement("div");
    this.scrubFill.className = "vr-scrub-fill";
    track.appendChild(this.scrubFill);
    this.scrubKnob = document.createElement("div");
    this.scrubKnob.className = "vr-scrub-knob";
    scrub.append(track, this.scrubKnob);
    const seekToX = (clientX) => {
      if (!this.s.frameCount) return;
      const r = scrub.getBoundingClientRect();
      const frac = Math.min(1, Math.max(0, (clientX - r.left) / r.width));
      this.seek(Math.round(frac * (this.s.frameCount - 1)));
    };
    scrub.addEventListener("pointerdown", (e) => {
      e.stopPropagation();
      this.root.focus();
      this.scrubbing = true;
      seekToX(e.clientX);
      try { scrub.setPointerCapture(e.pointerId); } catch {}
    });
    scrub.addEventListener("pointermove", (e) => {
      if (this.scrubbing) { e.stopPropagation(); seekToX(e.clientX); }
    });
    const endScrub = (e) => {
      if (this.scrubbing) {
        this.scrubbing = false;
        try { scrub.releasePointerCapture(e.pointerId); } catch {}
      }
    };
    scrub.addEventListener("pointerup", endScrub);
    scrub.addEventListener("pointercancel", endScrub);
    gScrub.appendChild(scrub);

    this.counterEl = document.createElement("span");
    this.counterEl.className = "vr-counter";
    this.counterEl.textContent = "– / –";
    gScrub.appendChild(this.counterEl);

    const fpsSel = (this.fpsSel = document.createElement("select"));
    fpsSel.title = "Playback FPS";
    for (const f of FPS_OPTIONS) {
      const o = document.createElement("option");
      o.value = String(f);
      o.textContent = `${f} fps`;
      fpsSel.appendChild(o);
    }
    fpsSel.value = "24";
    fpsSel.addEventListener("change", (e) => {
      e.stopPropagation();
      this.s.userFps = true;
      this.setFps(parseFloat(fpsSel.value));
    });
    fpsSel.addEventListener("pointerdown", (e) => e.stopPropagation());
    gOptions.appendChild(fpsSel);

    const modeSel = (this.modeSel = document.createElement("select"));
    modeSel.title = "Compare mode — wipe / side-by-side / difference / A-B flip. Press F to flip A/B.";
    for (const [value, label] of MODES) {
      const o = document.createElement("option");
      o.value = value;
      o.textContent = label;
      modeSel.appendChild(o);
    }
    modeSel.addEventListener("change", (e) => {
      e.stopPropagation();
      this.setMode(modeSel.value);
    });
    modeSel.addEventListener("pointerdown", (e) => e.stopPropagation());
    gOptions.appendChild(modeSel);

    this.btnLoop = btn(gOptions, "↻", LOOP_TOOLTIP, () => this.cycleLoopMode());
    this.#syncLoopBtn();

    this.btnFs = btn(gOptions, "⛶", "Fullscreen", () => this.toggleFullscreen());

    this.btnColor = btn(gOptions, "🎨", "Exposure / gamma controls", () =>
      this.#toggleColorBar()
    );

    // --- exposure/gamma row (hidden until 🎨 is toggled) ---
    const cbar = (this.colorBar = document.createElement("div"));
    cbar.className = "vr-colorbar";
    cbar.style.display = "none";
    cbar.addEventListener("pointerdown", (e) => e.stopPropagation());

    const slider = (labelText, min, max, step, value, fmt, onInput) => {
      const lab = document.createElement("label");
      lab.textContent = labelText;
      const r = document.createElement("input");
      r.type = "range";
      r.min = min; r.max = max; r.step = step; r.value = value;
      const val = document.createElement("span");
      val.className = "vr-cc-val";
      val.textContent = fmt(value);
      r.addEventListener("input", (e) => {
        e.stopPropagation();
        const v = parseFloat(r.value);
        val.textContent = fmt(v);
        onInput(v);
        this.#draw();
      });
      cbar.append(lab, r, val);
      return { range: r, val, fmt };
    };
    this.expCtl = slider("Exp", -6, 6, 0.1, 0, (v) => v.toFixed(1), (v) => (this.s.cp.exposure = v));
    this.gamCtl = slider("γ", 0.2, 4, 0.05, 1, (v) => v.toFixed(2), (v) => (this.s.cp.gamma = v));

    const resetBtn = document.createElement("button");
    resetBtn.textContent = "⟲";
    resetBtn.title = "Reset exposure and gamma";
    resetBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      this.s.cp.exposure = 0;
      this.s.cp.gamma = 1;
      this.expCtl.range.value = 0;
      this.expCtl.val.textContent = this.expCtl.fmt(0);
      this.gamCtl.range.value = 1;
      this.gamCtl.val.textContent = this.gamCtl.fmt(1);
      this.#draw();
    });
    cbar.appendChild(resetBtn);

    // --- collapsible info section (very bottom) ---
    const info = document.createElement("div");
    info.className = "vr-info";
    const infoHeader = (this.infoHeader = document.createElement("div"));
    infoHeader.className = "vr-info-header";
    this.infoLabel = document.createElement("span");
    this.infoLabel.textContent = "▸ Info";
    this.infoWarn = document.createElement("span");
    this.infoWarn.className = "vr-info-warn";
    this.infoWarn.style.display = "none";
    infoHeader.append(this.infoLabel, this.infoWarn);
    infoHeader.addEventListener("click", (e) => {
      e.stopPropagation();
      this.#toggleInfo();
    });
    const infoBody = (this.infoBody = document.createElement("div"));
    infoBody.className = "vr-info-body";
    infoBody.style.display = "none";
    infoBody.innerHTML = '<span class="vr-dim">Run the workflow to load clip info.</span>';
    info.append(infoHeader, infoBody);

    // --- RotoTools: roto view / background / download row and the history strip ---
    const rr = (this.rrBar = document.createElement("div"));
    rr.className = "rr-bar";
    rr.addEventListener("pointerdown", (e) => e.stopPropagation());
    this.rrName = document.createElement("span");
    this.rrName.className = "rr-name";
    const rrSelect = (title, options, value, onChange) => {
      const sel = document.createElement("select");
      sel.title = title;
      for (const [v, label, tip] of options) {
        const o = document.createElement("option");
        o.value = v;
        o.textContent = label;
        if (tip) o.title = tip;
        sel.appendChild(o);
      }
      sel.value = value;
      sel.addEventListener("change", (e) => {
        e.stopPropagation();
        onChange(sel.value);
      });
      return sel;
    };
    this.rrViewLab = document.createElement("label");
    this.rrViewLab.textContent = "B";
    this.rrViewSel = rrSelect("How the roto (B) is shown", B_VIEWS, this.s.bView, (v) => {
      this.s.bView = v;
      this.#syncRotoUi();
      this.#refreshB();
    });
    this.rrBgLab = document.createElement("label");
    this.rrBgLab.textContent = "BG";
    this.rrBgSel = rrSelect("Background behind the roto in the player",
      BACKGROUNDS, this.s.bg, (v) => {
        this.s.bg = v;
        this.#refreshB();
      });
    this.rrDlSel = rrSelect("What to download", DOWNLOAD_KINDS, "roto_alpha", () => {});
    this.rrDlBtn = document.createElement("button");
    this.rrDlBtn.textContent = "⤓ Download";
    this.rrDlBtn.title = "Makes the video now and saves it to your browser's Downloads folder (nothing is kept in ComfyUI)";
    this.rrDlBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      this.#download();
    });
    rr.append(this.rrName, this.rrViewLab, this.rrViewSel, this.rrBgLab, this.rrBgSel, this.rrDlSel, this.rrDlBtn);
    const hist = (this.rrHist = document.createElement("div"));
    hist.className = "rr-hist";
    hist.addEventListener("pointerdown", (e) => e.stopPropagation());
    hist.innerHTML = '<span class="rr-empty">Shots reviewed in this session will appear here.</span>';
    this.#syncRotoUi();

    root.append(viewport, controls, rr, cbar, hist, info);

    // --- viewport interaction (wipe drag) ---
    canvas.addEventListener("pointerdown", (e) => {
      e.stopPropagation();
      this.root.focus();
      if (this.s.mode === "wipeH" || this.s.mode === "wipeV") {
        this.dragging = true;
        this.#wipeFromEvent(e); // place wipe before capture: capture can throw
        try {
          canvas.setPointerCapture(e.pointerId);
        } catch {}
      }
    });
    canvas.addEventListener("pointermove", (e) => {
      if (this.dragging) {
        e.stopPropagation();
        this.#wipeFromEvent(e);
      }
    });
    canvas.addEventListener("pointerup", (e) => {
      if (this.dragging) {
        this.dragging = false;
        canvas.releasePointerCapture(e.pointerId);
      }
    });
    // Deliberately NOT intercepting wheel: graph zoom must keep working.

    // --- keyboard (root element only; never the document) ---
    root.addEventListener("keydown", (e) => {
      let handled = true;
      switch (e.key) {
        case "ArrowLeft":
          this.step(-1);
          break;
        case "ArrowRight":
          this.step(1);
          break;
        case " ":
          this.togglePlay();
          break;
        case "Home":
          this.seek(0);
          break;
        case "End":
          this.seek(this.s.frameCount - 1);
          break;
        case "f":
        case "F":
          // Flip A/B (enters A/B Flip mode if needed). Only with two streams.
          if (this.s.b.length) {
            if (this.s.mode !== "abflip") this.setMode("abflip");
            this.#toggleAB();
          }
          break;
        default:
          handled = false;
      }
      if (handled) {
        e.preventDefault();
        e.stopPropagation();
      }
    });
  }

  #wipeFromEvent(e) {
    const r = this.canvas.getBoundingClientRect();
    if (this.s.mode === "wipeV") {
      this.s.wipe = Math.min(1, Math.max(0, (e.clientY - r.top) / r.height));
    } else {
      this.s.wipe = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    }
    this.#draw();
  }

  #toggleAB() {
    this.s.abShow = this.s.abShow === "a" ? "b" : "a";
    this.flipBtn.textContent = this.s.abShow.toUpperCase();
    this.#draw();
  }

  #toggleInfo() {
    this.infoOpen = !this.infoOpen;
    this.infoBody.style.display = this.infoOpen ? "" : "none";
    this.infoLabel.textContent = (this.infoOpen ? "▾ " : "▸ ") + "Info";
  }

  #toggleColorBar() {
    const show = this.colorBar.style.display === "none";
    this.colorBar.style.display = show ? "" : "none";
    this.btnColor.classList.toggle("vr-on", show);
  }

  #getEngine() {
    if (!this.engine && !this.engineFailed) {
      this.engine = new VRColorEngine();
      if (!this.engine.ok) {
        this.engineFailed = true;
        this.engine = null;
        console.warn("[videoreview] WebGL unavailable — exposure/gamma controls disabled.");
      }
    }
    return this.engine;
  }

  // RotoTools: the roto frame as chosen in the B row (over a background, or its matte). Cached per frame;
  // a new canvas per view/background so the colour engine never reuses a stale texture.
  #bView(entry, img) {
    if (!this.s.bAlpha || this.s.bView === "rgba") return img;
    const key = `${this.s.bView}|${this.s.bg}`;
    if (entry.rr?.key === key) return entry.rr.canvas;
    const w = img.naturalWidth, h = img.naturalHeight;
    const c = document.createElement("canvas");
    c.width = w;
    c.height = h;
    const g = c.getContext("2d");
    if (this.s.bView === "alpha") {
      g.fillStyle = "#000";
      g.fillRect(0, 0, w, h);
      const t = document.createElement("canvas");
      t.width = w;
      t.height = h;
      const tg = t.getContext("2d");
      tg.drawImage(img, 0, 0);
      tg.globalCompositeOperation = "source-in"; // keep only the alpha, painted white
      tg.fillStyle = "#fff";
      tg.fillRect(0, 0, w, h);
      g.drawImage(t, 0, 0);
    } else {
      if (this.s.bg === "checker") {
        const sz = Math.max(8, Math.round(Math.min(w, h) / 40));
        for (let y = 0; y < h; y += sz) {
          for (let x = 0; x < w; x += sz) {
            g.fillStyle = (x / sz + y / sz) % 2 ? "#9a9a9a" : "#d6d6d6";
            g.fillRect(x, y, sz, sz);
          }
        }
      } else {
        g.fillStyle = this.s.bg;
        g.fillRect(0, 0, w, h);
      }
      g.drawImage(img, 0, 0);
    }
    entry.rr = { key, canvas: c };
    return c;
  }

  #refreshB() {
    this.engine?.clearCache();
    this.#draw();
  }

  #syncRotoUi() {
    const roto = this.s.bAlpha;
    for (const el of [this.rrViewLab, this.rrViewSel]) el.style.display = roto ? "" : "none";
    const bgShown = roto && this.s.bView === "roto";
    for (const el of [this.rrBgLab, this.rrBgSel]) el.style.display = bgShown ? "" : "none";
    this.rrName.textContent = this.s.name || "";
    this.rrName.title = this.s.name || "";
    // both downloads are made from the roto (B); without it there is nothing to download
    const hasB = this.s.b.length > 0;
    this.rrDlSel.disabled = !hasB;
    this.rrDlBtn.disabled = !this.s.runId || !hasB;
  }

  async #download() {
    if (!this.s.runId) return;
    const kind = this.rrDlSel.value;
    const url = this.api.apiURL(`/rototools/review/download?run=${encodeURIComponent(this.s.runId)}` +
      `&kind=${encodeURIComponent(kind)}`);
    const label = this.rrDlBtn.textContent;
    this.rrDlBtn.disabled = true;
    this.rrDlBtn.textContent = "Making the video…";
    try {
      const r = await fetch(url);
      if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
      const blob = await r.blob();
      const cd = r.headers.get("Content-Disposition") || "";
      const name = (cd.match(/filename="([^"]+)"/) || [])[1] || `${this.s.name || "roto"}_${kind}`;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
      console.info("[RotoReview] downloaded", name);
    } catch (e) {
      console.error("[RotoReview] download failed", e);
      alert("Download failed: " + e.message);
    } finally {
      this.rrDlBtn.textContent = label;
      this.rrDlBtn.disabled = false;
    }
  }

  // RotoTools: the history strip (newest first). Clicking a shot loads it into the player.
  setHistory(runs) {
    this.s.history = runs;
    const hist = this.rrHist;
    hist.textContent = "";
    if (!runs.length) {
      hist.innerHTML = '<span class="rr-empty">Shots reviewed in this session will appear here.</span>';
      return;
    }
    for (const run of runs) {
      const f = run.a_frames[0];
      const h = document.createElement("div");
      h.className = "rr-h";
      h.classList.toggle("rr-cur", run.run_id?.[0] === this.s.runId);
      h.title = `${run.name?.[0] ?? ""} · ${run.a_frames.length} frames` +
        (run.time ? ` · ${new Date(run.time[0] * 1000).toLocaleTimeString()}` : "");
      const img = document.createElement("img");
      img.loading = "lazy";
      img.src = this.api.apiURL(`/view?filename=${encodeURIComponent(f.filename)}&type=${f.type}` +
        `&subfolder=${encodeURIComponent(f.subfolder ?? "")}`);
      const label = document.createElement("span");
      label.textContent = run.name?.[0] ?? "";
      h.append(img, label);
      h.addEventListener("click", (e) => {
        e.stopPropagation();
        this.load(run);
        this.root.focus();
      });
      hist.appendChild(h);
    }
  }

  #markHistory() {
    for (const [i, el] of [...this.rrHist.querySelectorAll(".rr-h")].entries()) {
      el.classList.toggle("rr-cur", this.s.history[i]?.run_id?.[0] === this.s.runId);
    }
  }

  // Display source for an entry: the raw Image when no adjustment is active,
  // otherwise the WebGL-transformed canvas.
  #src(entry) {
    let img = entry?.img;
    if (!img?.naturalWidth) return img;
    if (entry.isB) img = this.#bView(entry, img); // RotoTools: roto over background / matte
    const { exposure, gamma } = this.s.cp;
    if (exposure === 0 && gamma === 1) return img; // identity — skip the GPU
    const engine = this.#getEngine();
    return engine?.transform(img, this.s.cp) || img;
  }

  #updateInfo() {
    const i = this.s.info;
    if (!i) {
      this.infoBody.innerHTML = '<span class="vr-dim">Run the workflow to load clip info.</span>';
      return;
    }
    // Actual source resolution, with the playback (encoded) resolution in brackets.
    const res = (w, h, prev) => {
      const base = w && h ? `${w}×${h}` : "—";
      return prev && prev[0]
        ? `${base} <span class="vr-dim">(${prev[0]}×${prev[1]})</span>`
        : base;
    };
    const rows = [
      `<div><span class="vr-k">A</span> &nbsp;${res(i.aW, i.aH, i.aPrev)} &nbsp;·&nbsp; ${i.aCount} frames</div>`,
    ];
    if (i.bCount != null) {
      rows.push(
        `<div><span class="vr-k">B</span> &nbsp;${res(i.bW, i.bH, i.bPrev)} &nbsp;·&nbsp; ${i.bCount} frames</div>`
      );
    }
    rows.push(
      `<div class="vr-dim">Base fps ${i.baseFps} &nbsp;·&nbsp; timeline ${this.s.frameCount} frames</div>`
    );
    this.infoBody.innerHTML = rows.join("");
  }

  // ------------------------------------------------------------ load/unload

  load(payload) {
    const aList = payload?.a_frames ?? [];
    const bList = payload?.b_frames ?? [];
    if (!aList.length) return;

    this.pause();
    this.s.generation++;
    this.#abortPending();
    // New frame set replaces the old one — free stale GPU textures now rather
    // than waiting for LRU eviction.
    this.engine?.clearCache();

    const toEntry = (f) => ({
      url: this.api.apiURL(
        `/view?filename=${encodeURIComponent(f.filename)}&type=${f.type}&subfolder=${encodeURIComponent(
          f.subfolder ?? ""
        )}`
      ),
      img: null,
      status: "pending",
    });
    this.s.a = aList.map(toEntry);
    this.s.b = bList.map(toEntry);
    // RotoTools: mark B frames, remember which run and shot this is
    for (const e of this.s.b) e.isB = true;
    this.s.bAlpha = !!payload.b_alpha?.[0];
    this.s.runId = payload.run_id?.[0] ?? null;
    this.s.name = payload.name?.[0] ?? "";
    this.#syncRotoUi();
    this.#markHistory();
    this.s.frameCount = Math.max(this.s.a.length, this.s.b.length);
    this.s.cur = 0;
    this.s.abShow = "a";
    this.s.loaded = 0;
    this.s.errored = 0;
    this.s.total = this.s.a.length + this.s.b.length;

    const aSize = payload.a_size?.[0];
    const bSize = payload.b_size?.[0];
    if (aSize?.[0] > 0) this.s.aspect = aSize[1] / aSize[0];

    const nodeFps = payload.fps?.[0];
    if (nodeFps && !this.s.userFps) this.setFps(nodeFps);

    // Clip info for the collapsible panel.
    this.s.info = {
      aW: aSize?.[0],
      aH: aSize?.[1],
      aPrev: payload.a_prev?.[0],
      aCount: this.s.a.length,
      bW: this.s.b.length ? bSize?.[0] : null,
      bH: this.s.b.length ? bSize?.[1] : null,
      bPrev: this.s.b.length ? payload.b_prev?.[0] : null,
      bCount: this.s.b.length ? this.s.b.length : null,
      baseFps: nodeFps ?? this.s.fps,
    };
    this.#updateInfo();

    // Mismatch warning — shown in the info bar (never silently conformed).
    const warns = [];
    if (this.s.b.length && this.s.a.length !== this.s.b.length) {
      warns.push(`A ${this.s.a.length}f · B ${this.s.b.length}f`);
    }
    if (aSize && bSize && (aSize[0] !== bSize[0] || aSize[1] !== bSize[1])) {
      warns.push(`A ${aSize[0]}×${aSize[1]} · B ${bSize[0]}×${bSize[1]}`);
    }
    const warnText = warns.join("  ·  ");
    this.infoWarn.textContent = warnText ? `⚠ ${warnText}` : "";
    this.infoWarn.style.display = warnText ? "" : "none";

    // Single-stream mode: hide compare-mode select when there is no B.
    this.modeSel.style.display = this.s.b.length ? "" : "none";
    // Keep flip button state consistent with the current mode.
    this.flipBtn.textContent = "A";
    this.flipBtn.style.display = this.s.mode === "abflip" && this.s.b.length ? "" : "none";

    // Interleave A/B so the first frames of both streams arrive first.
    this.queue = [];
    for (let i = 0; i < this.s.frameCount; i++) {
      if (i < this.s.a.length) this.queue.push(this.s.a[i]);
      if (i < this.s.b.length) this.queue.push(this.s.b[i]);
    }
    this.#updateProgress();
    this.#pumpQueue();

    this.#syncTransportUi();
    this.#draw();
  }

  destroy() {
    this.pause();
    this.s.generation++;
    this.#abortPending();
    this.ro.disconnect();
    document.removeEventListener("fullscreenchange", this.onFsChange);
    if (document.fullscreenElement === this.root) document.exitFullscreen?.();
    this.engine?.dispose();
    this.engine = null;
  }

  #abortPending() {
    for (const list of [this.s.a, this.s.b]) {
      for (const e of list) {
        if (e.status === "pending" && e.img) e.img.src = "";
      }
    }
    this.queue = [];
    this.inflight = 0;
  }

  #pumpQueue() {
    const gen = this.s.generation;
    while (this.inflight < MAX_CONCURRENT_LOADS && this.queue.length) {
      const entry = this.queue.shift();
      if (entry.status !== "pending" || entry.img) continue;
      const img = new Image();
      img.decoding = "async";
      entry.img = img;
      this.inflight++;
      const done = (ok) => {
        if (gen !== this.s.generation) return; // stale generation
        this.inflight--;
        entry.status = ok ? "ok" : "err";
        if (ok) this.s.loaded++;
        else this.s.errored++;
        this.#updateProgress();
        // Redraw if this frame is currently displayed.
        const aIdx = this.s.a.indexOf(entry);
        const bIdx = this.s.b.indexOf(entry);
        const shownA = this.s.cur < this.s.a.length ? this.s.cur : -1;
        const shownB = this.s.cur < this.s.b.length ? this.s.cur : -1;
        if (aIdx === shownA || bIdx === shownB) this.#draw();
        this.#pumpQueue();
      };
      img.onload = () => done(true);
      img.onerror = () => done(false);
      img.src = entry.url;
    }
  }

  #prioritize(index) {
    // Move the current frame pair to the front of the pending queue.
    const wanted = [];
    if (index < this.s.a.length) wanted.push(this.s.a[index]);
    if (index < this.s.b.length) wanted.push(this.s.b[index]);
    for (const e of wanted.reverse()) {
      const qi = this.queue.indexOf(e);
      if (qi > 0) {
        this.queue.splice(qi, 1);
        this.queue.unshift(e);
      }
    }
    this.#pumpQueue();
  }

  #updateProgress() {
    const { loaded, errored, total } = this.s;
    const doneCount = loaded + errored;
    if (!total) {
      this.#showMessage("Run workflow to load frames");
      return;
    }
    const firstA = this.s.a[0];
    if ((firstA && firstA.status === "err") || (errored === total && total > 0)) {
      // temp files are gone (typically after a server restart)
      this.#showMessage("Frames unavailable — re-run the workflow");
      return;
    }
    if (doneCount < total) {
      this.overlayEl.style.display = "";
      this.overlayText.textContent = `Loading ${doneCount}/${total}`;
      this.progressBar.style.display = "";
      this.progressFill.style.width = `${Math.round((doneCount / total) * 100)}%`;
    } else {
      this.overlayEl.style.display = "none";
    }
  }

  #showMessage(text) {
    this.overlayEl.style.display = "";
    this.overlayText.textContent = text;
    this.progressBar.style.display = "none";
  }

  // ------------------------------------------------------------- transport

  play(dir = 1) {
    if (!this.s.frameCount) return;
    this.s.dir = dir;
    this.s.playDir = dir; // remember the pressed direction (bounce flips s.dir)
    if (!this.s.playing) {
      this.s.playing = true;
      this.lastTs = performance.now();
      this.acc = 0;
      this.raf = requestAnimationFrame(this.#tick);
    }
    this.#syncTransportUi();
  }

  pause() {
    this.s.playing = false;
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0;
    this.#syncTransportUi();
  }

  togglePlay() {
    if (this.s.playing) this.pause();
    else this.play(this.s.playDir || 1);
  }

  // Play in `dir`; if already playing that direction, pause (so the same button
  // toggles play/pause).
  togglePlayDir(dir) {
    if (this.s.playing && this.s.playDir === dir) this.pause();
    else this.play(dir);
  }

  toggleFullscreen() {
    if (document.fullscreenElement === this.root) document.exitFullscreen?.();
    else this.root.requestFullscreen?.();
  }

  step(delta) {
    if (!this.s.frameCount) return;
    this.pause();
    const n = this.s.frameCount;
    let next = this.s.cur + delta;
    // Manual stepping wraps only in Loop mode; clamps in Once/Bounce.
    if (this.s.loopMode === "loop") next = ((next % n) + n) % n;
    else next = Math.min(n - 1, Math.max(0, next));
    this.s.cur = next;
    this.#prioritize(next);
    this.#syncTransportUi();
    this.#draw();
  }

  seek(index) {
    if (!this.s.frameCount) return;
    this.pause();
    this.s.cur = Math.min(this.s.frameCount - 1, Math.max(0, index));
    this.#prioritize(this.s.cur);
    this.#syncTransportUi();
    this.#draw();
  }

  setFps(fps) {
    this.s.fps = fps;
    // Inject a non-standard rate (e.g. 30 from the node widget) into the select.
    if (![...this.fpsSel.options].some((o) => parseFloat(o.value) === fps)) {
      const o = document.createElement("option");
      o.value = String(fps);
      o.textContent = `${fps} fps`;
      this.fpsSel.appendChild(o);
    }
    this.fpsSel.value = String(fps);
  }

  setMode(mode) {
    this.s.mode = mode;
    this.modeSel.value = mode;
    this.flipBtn.style.display = mode === "abflip" && this.s.b.length ? "" : "none";
    if (mode === "abflip") this.flipBtn.textContent = this.s.abShow.toUpperCase();
    this.canvas.style.cursor =
      mode === "wipeH" ? "ew-resize" : mode === "wipeV" ? "ns-resize" : "default";
    this.#draw();
  }

  cycleLoopMode() {
    const idx = LOOP_MODES.findIndex(([m]) => m === this.s.loopMode);
    this.s.loopMode = LOOP_MODES[(idx + 1) % LOOP_MODES.length][0];
    this.#syncLoopBtn();
  }

  #syncLoopBtn() {
    const [mode, icon] = LOOP_MODES.find(([m]) => m === this.s.loopMode);
    this.btnLoop.textContent = icon;
    // Tooltip stays the static LOOP_TOOLTIP (lists all three modes); the current
    // mode is shown by the icon + highlight.
    this.btnLoop.classList.toggle("vr-on", mode !== "once");
  }

  #tick = (ts) => {
    if (!this.s.playing) return;
    this.acc += ts - this.lastTs;
    this.lastTs = ts;
    const dur = 1000 / this.s.fps;
    if (this.acc > 4 * dur) this.acc = dur; // clamp after a background-tab stall
    let advanced = false;
    while (this.acc >= dur) {
      this.acc -= dur;
      this.#advance();
      advanced = true;
      if (!this.s.playing) break; // hit a non-looping end
    }
    if (advanced) {
      this.#syncTransportUi();
      this.#draw();
    }
    if (this.s.playing) this.raf = requestAnimationFrame(this.#tick);
  };

  #advance() {
    const n = this.s.frameCount;
    if (n <= 1) return;
    const next = this.s.cur + this.s.dir;
    if (this.s.loopMode === "bounce") {
      if (next < 0) {
        this.s.dir = 1;
        this.s.cur = Math.min(n - 1, 1);
      } else if (next >= n) {
        this.s.dir = -1;
        this.s.cur = Math.max(0, n - 2);
      } else {
        this.s.cur = next;
      }
    } else if (this.s.loopMode === "loop") {
      this.s.cur = ((next % n) + n) % n;
    } else {
      // once
      if (next < 0 || next >= n) this.pause(); // hold at the end
      else this.s.cur = next;
    }
  }

  #syncTransportUi() {
    const { cur, frameCount, playing, playDir } = this.s;
    this.counterEl.textContent = frameCount ? `${cur + 1} / ${frameCount}` : "– / –";
    const frac = frameCount > 1 ? cur / (frameCount - 1) : 0;
    this.scrubFill.style.width = `${frac * 100}%`;
    this.scrubKnob.style.left = `${frac * 100}%`;
    const fwdOn = playing && playDir === 1;
    const revOn = playing && playDir === -1;
    this.btnPlayFwd.textContent = fwdOn ? "⏸" : "▶";
    this.btnPlayRev.textContent = revOn ? "⏸" : "◀";
    this.btnPlayFwd.classList.toggle("vr-on", fwdOn);
    this.btnPlayRev.classList.toggle("vr-on", revOn);
  }

  // ---------------------------------------------------------------- render

  #resizeCanvas() {
    const dpr = window.devicePixelRatio || 1;
    const w = this.viewportEl.clientWidth;
    const h = this.viewportEl.clientHeight;
    if (!w || !h) return;
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.#draw();
  }

  #entryAt(list, index) {
    // Out of range -> null so the shorter stream goes black past its last frame.
    return index < list.length ? list[index] : null;
  }

  #draw() {
    const ctx = this.ctx;
    const W = this.viewportEl.clientWidth;
    const H = this.viewportEl.clientHeight;
    if (!W || !H) return;
    ctx.fillStyle = "#111";
    ctx.fillRect(0, 0, W, H);
    if (!this.s.frameCount) return;

    const a = this.#entryAt(this.s.a, this.s.cur);
    const b = this.#entryAt(this.s.b, this.s.cur);
    const single = !this.s.b.length;
    const mode = single ? "single" : this.s.mode;

    if (mode === "single") {
      this.#blit(ctx, a, 0, 0, W, H);
      return;
    }

    if (mode === "abflip") {
      // Full-frame single stream; the on-screen flip button is the A/B label.
      this.#blit(ctx, this.s.abShow === "a" ? a : b, 0, 0, W, H);
      return;
    }

    if (mode === "side") {
      this.#blit(ctx, a, 0, 0, W / 2, H);
      this.#blit(ctx, b, W / 2, 0, W / 2, H);
      this.#label(ctx, "A", { x: 0, y: 0, w: W / 2, h: H });
      this.#label(ctx, "B", { x: W / 2, y: 0, w: W / 2, h: H }, true);
      ctx.strokeStyle = "rgba(255,255,255,0.25)";
      ctx.beginPath();
      ctx.moveTo(W / 2, 0);
      ctx.lineTo(W / 2, H);
      ctx.stroke();
      return;
    }

    // Shared reference frame: A and B are drawn at MATCHED HEIGHTS (both the same
    // display height, widths following each aspect), centered and overlaid. The
    // shared height scales with the node, so resizing zooms both together and
    // never changes their relative sizes.
    const { rectA, rectB } = this.#refRects(W, H);

    if (mode === "diff") {
      this.#blitInto(ctx, a, rectA);
      const prev = ctx.globalCompositeOperation;
      ctx.globalCompositeOperation = "difference";
      this.#blitInto(ctx, b, rectB);
      ctx.globalCompositeOperation = prev;
      return;
    }

    // wipeH / wipeV — split at the wipe line: A on the near side, B on the far
    // side, each in its fixed-scale rect. Empty area / out-of-range stays black.
    const horizontal = mode === "wipeH";
    const cut = horizontal ? W * this.s.wipe : H * this.s.wipe;
    ctx.save();
    ctx.beginPath();
    if (horizontal) ctx.rect(0, 0, cut, H);
    else ctx.rect(0, 0, W, cut);
    ctx.clip();
    this.#blitInto(ctx, a, rectA);
    ctx.restore();
    ctx.save();
    ctx.beginPath();
    if (horizontal) ctx.rect(cut, 0, W - cut, H);
    else ctx.rect(0, cut, W, H - cut);
    ctx.clip();
    this.#blitInto(ctx, b, rectB);
    ctx.restore();

    // Divider + grab handle across the full viewport (difference composite so it
    // stays visible on any content).
    const prev = ctx.globalCompositeOperation;
    ctx.globalCompositeOperation = "difference";
    ctx.strokeStyle = "#fff";
    ctx.beginPath();
    if (horizontal) {
      ctx.moveTo(cut, 0);
      ctx.lineTo(cut, H);
    } else {
      ctx.moveTo(0, cut);
      ctx.lineTo(W, cut);
    }
    ctx.stroke();
    ctx.globalCompositeOperation = prev;
    ctx.fillStyle = "#fff";
    ctx.beginPath();
    if (horizontal) ctx.arc(cut, H / 2, 4, 0, Math.PI * 2);
    else ctx.arc(W / 2, cut, 4, 0, Math.PI * 2);
    ctx.fill();

    this.#label(ctx, "A", { x: 0, y: 0, w: W, h: H });
    this.#label(ctx, "B", { x: 0, y: 0, w: W, h: H }, true);
  }

  // Computes matched-HEIGHT rects for A and B: both streams are drawn at the same
  // display height (widths follow each aspect ratio), centered and overlaid. The
  // shared height scales with the viewport, so resizing the node zooms both
  // together and never changes their relative sizes.
  #refRects(W, H) {
    const info = this.s.info || {};
    const aAsp = info.aW && info.aH ? info.aW / info.aH : 0;
    const bAsp = info.bW && info.bH ? info.bW / info.bH : 0;
    const compW = Math.max(aAsp, bAsp); // width of the widest stream at height 1
    if (!compW) return { rectA: null, rectB: null };
    const s = Math.min(W / compW, H); // shared display height
    const boxX = (W - compW * s) / 2, boxY = (H - s) / 2;
    const place = (asp) =>
      asp ? { x: boxX + (compW * s - asp * s) / 2, y: boxY, w: asp * s, h: s } : null;
    return { rectA: place(aAsp), rectB: place(bAsp) };
  }

  // Draws one entry into an explicit, already aspect-correct rect. Null entry or
  // null rect -> nothing drawn (stays black).
  #blitInto(ctx, entry, rect) {
    if (!entry || !rect) return;
    if (entry.status === "ok" && entry.img?.naturalWidth) {
      ctx.drawImage(this.#src(entry), rect.x, rect.y, rect.w, rect.h);
      return;
    }
    ctx.fillStyle = "#1a1a1a";
    ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
    ctx.fillStyle = "#555";
    ctx.font = "11px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(entry.status === "err" ? "missing" : "loading…", rect.x + rect.w / 2, rect.y + rect.h / 2);
  }

  // Draws one entry letterboxed into the given box, preserving its OWN aspect
  // ratio (black bars fill the remainder). Returns the drawn rect, or null when
  // there is nothing to draw (null entry / out of range -> stays black).
  #blit(ctx, entry, x, y, w, h) {
    if (!entry) return null;
    if (entry.status === "ok" && entry.img?.naturalWidth) {
      const r = fitRect(entry.img.naturalWidth, entry.img.naturalHeight, x, y, w, h);
      ctx.drawImage(this.#src(entry), r.x, r.y, r.w, r.h);
      return r;
    }
    // Placeholder for a frame that is still loading or missing.
    const r = fitRect(16, 16 * this.s.aspect, x, y, w, h);
    ctx.fillStyle = "#1a1a1a";
    ctx.fillRect(r.x, r.y, r.w, r.h);
    ctx.fillStyle = "#555";
    ctx.font = "11px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(
      entry.status === "err" ? "missing" : "loading…",
      r.x + r.w / 2,
      r.y + r.h / 2
    );
    return r;
  }

  #label(ctx, text, rect, right = false) {
    if (!rect) return;
    ctx.font = "bold 11px sans-serif";
    ctx.textBaseline = "top";
    ctx.textAlign = right ? "right" : "left";
    const x = right ? rect.x + rect.w - 6 : rect.x + 6;
    ctx.fillStyle = "rgba(0,0,0,0.6)";
    const tw = ctx.measureText(text).width;
    ctx.fillRect(right ? x - tw - 3 : x - 3, rect.y + 4, tw + 6, 15);
    ctx.fillStyle = "#fff";
    ctx.fillText(text, x, rect.y + 6);
  }
}
