/* Live games: dodge-native's Rust engine and every bot, compiled to one
   WebAssembly module (inlined by build.py as base64). One Sim per widget;
   widgets start when their slide becomes current and are destroyed when it is
   left. */
(function () {
  const WASM_B64 = "/*WASM_B64*/";
  const WORKER_B64 = "/*WORKER_B64*/";
  const BOTS = { human: 0, m0: 1, space: 2, cnn: 3, belief: 4, lookahead: 5, landscape: 6, random: 7 };
  // A deck may rename bots on screen by setting window.DODGE_NAMES before this script runs.
  const NAMES = Object.assign({ human: "You", m0: "M0", space: "SpaceBot", cnn: "CNN v2-best", belief: "Belief planner", lookahead: "Lookahead", landscape: "Landscape", random: "Random" }, window.DODGE_NAMES || {});
  const CAUSES = ["normal enemy", "kamikaze", "kamikaze blast", "static pattern", "moving pattern", "unknown"];
  // learning/dodge/colormap.py VIRIDIS, the 256 x RGB table exactly as numpy builds it
  const VIRIDIS = new Uint8Array([68,1,84,68,2,85,68,4,87,68,5,88,69,7,89,69,8,90,69,9,92,69,11,93,69,12,94,69,13,95,69,15,97,70,16,98,70,18,99,70,19,101,70,20,102,70,22,103,70,23,104,70,24,106,71,26,107,71,27,108,71,29,109,71,30,111,71,31,112,71,33,113,71,34,114,72,35,116,72,37,117,72,38,118,72,40,120,72,41,120,71,42,121,71,43,122,71,44,122,70,46,123,70,47,123,70,48,124,69,49,125,69,50,125,69,52,126,68,53,126,68,54,127,68,55,128,67,56,128,67,58,129,66,59,129,66,60,130,66,61,131,65,62,131,65,64,132,65,65,132,64,66,133,64,67,134,64,68,134,63,70,135,63,71,135,63,72,136,62,73,137,62,74,137,61,75,137,61,76,137,60,78,138,60,79,138,60,80,138,59,81,138,59,82,138,58,83,138,58,84,139,57,85,139,57,86,139,56,87,139,56,88,139,55,89,140,55,90,140,55,91,140,54,92,140,54,93,140,53,94,140,53,96,141,52,97,141,52,98,141,51,99,141,51,100,141,50,101,141,50,102,142,49,103,142,49,104,142,49,105,142,48,106,142,48,107,142,47,108,142,47,109,142,47,110,142,46,110,142,46,111,142,46,112,142,45,113,142,45,114,142,44,115,142,44,116,142,44,117,142,43,118,142,43,119,142,42,120,142,42,121,142,42,121,142,41,122,142,41,123,142,40,124,142,40,125,142,40,126,142,39,127,142,39,128,142,39,129,142,38,130,142,38,131,142,38,132,142,37,133,142,37,134,141,37,135,141,37,136,141,36,137,141,36,138,141,36,139,140,36,140,140,35,141,140,35,142,140,35,143,140,35,144,140,34,144,139,34,145,139,34,146,139,34,147,139,33,148,139,33,149,139,33,150,138,33,151,138,32,152,138,32,153,138,32,154,138,32,155,137,31,156,137,31,157,137,31,158,137,32,159,136,33,160,136,34,161,135,34,162,135,35,163,134,36,164,133,37,164,133,37,165,132,38,166,132,39,167,131,40,168,131,41,169,130,41,170,129,42,171,129,43,172,128,44,172,128,44,173,127,45,174,127,46,175,126,47,176,126,48,177,125,48,178,124,49,179,124,50,179,123,51,180,123,51,181,122,52,182,122,53,183,121,55,184,120,57,185,119,59,185,118,61,186,116,63,187,115,65,188,114,67,188,113,69,189,112,71,190,111,73,191,110,75,192,109,77,192,107,79,193,106,81,194,105,83,195,104,85,195,103,87,196,102,89,197,101,91,198,100,93,199,98,95,199,97,96,200,96,98,201,95,100,202,94,102,202,93,104,203,92,106,204,91,108,205,89,111,205,88,113,206,86,116,207,85,118,207,83,121,208,82,123,208,80,126,209,78,128,210,77,131,210,75,133,211,74,136,211,72,138,212,70,141,213,69,143,213,67,146,214,66,148,214,64,151,215,63,153,216,61,156,216,59,158,217,58,161,217,56,163,218,55,166,219,53,168,219,51,171,220,50,173,220,48,176,221,47,178,222,45,181,222,44,183,222,44,186,223,43,189,223,43,191,223,43,194,224,43,196,224,42,199,224,42,201,225,42,204,225,42,207,225,41,209,226,41,212,226,41,214,226,41,217,227,40,220,227,40,222,227,40,225,228,40,227,228,39,230,228,39,232,228,39,235,229,39,238,229,38,240,229,38,243,230,38,245,230,38,248,230,37,250,231,37,253,231,37]);
  // learning/dodge/display.py: the cart clears to palette index 12, and only
  // those pixels are replaced by the field
  const BACKGROUND_INDEX = 12;
  const f32 = Math.fround;
  // numpy's pairwise float32 sum (np.add.reduce on a contiguous float32 array)
  function pairwise(a, lo, n) {
    if (n < 8) {
      let s = -0;
      for (let i = 0; i < n; i++) s = f32(s + a[lo + i]);
      return s;
    }
    if (n <= 128) {
      const r = [];
      for (let j = 0; j < 8; j++) r.push(a[lo + j]);
      let i = 8;
      for (; i < n - (n % 8); i += 8) for (let j = 0; j < 8; j++) r[j] = f32(r[j] + a[lo + i + j]);
      let s = f32(f32(f32(r[0] + r[1]) + f32(r[2] + r[3])) + f32(f32(r[4] + r[5]) + f32(r[6] + r[7])));
      for (; i < n; i++) s = f32(s + a[lo + i]);
      return s;
    }
    let n2 = Math.floor(n / 2);
    n2 -= n2 % 8;
    return f32(pairwise(a, lo, n2) + pairwise(a, lo + n2, n - n2));
  }
  // Action::ALL is N L R U D UL UR DL DR; laid out as a compass
  const COMPASS = [5, 3, 6, 1, 0, 2, 7, 4, 8];
  const GLYPH = ["·", "←", "→", "↑", "↓", "↖", "↗", "↙", "↘"];
  const PAL = [[0, 0, 0], [29, 43, 83], [126, 37, 83], [0, 135, 81], [171, 82, 54], [95, 87, 79], [194, 195, 199], [255, 241, 232], [255, 0, 77], [255, 163, 0], [255, 236, 39], [0, 228, 54], [41, 173, 255], [131, 118, 156], [255, 119, 168], [255, 204, 170]];
  const reduced = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  let wasm = null;
  const ready = (async () => {
    const bin = Uint8Array.from(atob(WASM_B64), c => c.charCodeAt(0));
    const { instance } = await WebAssembly.instantiate(bin, {});
    wasm = instance.exports;
  })().catch(e => { console.error("wasm", e); });
  const workerBytes = Uint8Array.from(atob(WORKER_B64), c => c.charCodeAt(0));
  const workerUrl = URL.createObjectURL(new Blob([workerBytes], { type: "text/javascript" }));
  const workerLimit = (navigator.hardwareConcurrency || 2) - 2;

  const keys = new Set();
  function humanMask() {
    let m = 0;
    if (keys.has("ArrowLeft") || keys.has("a")) m |= 1;
    if (keys.has("ArrowRight") || keys.has("d")) m |= 2;
    if (keys.has("ArrowUp") || keys.has("w")) m |= 4;
    if (keys.has("ArrowDown") || keys.has("s")) m |= 8;
    if ((m & 3) === 3) m &= ~3;
    if ((m & 12) === 12) m &= ~12;
    return m;
  }

  function el(tag, cls, parent, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }

  function speedSelect(bar, current, onChange) {
    const sp = el("select", "", bar);
    sp.title = "Speed";
    for (const v of ["1", "2", "4", "16", "max"]) {
      const o = el("option", "", sp, v === "max" ? "max" : v + "×");
      o.value = v;
      if (v === current) o.selected = true;
    }
    sp.addEventListener("change", () => onChange(sp.value));
    return sp;
  }

  class Live {
    constructor(root, group) {
      this.root = root;
      this.group = group;
      this.kind = root.dataset.bot;
      this.bot = BOTS[this.kind];
      this.workerBacked = this.kind === "belief" && workerLimit > 0;
      this.worker = null;
      this.workerReady = false;
      this.workerStarting = false;
      this.workerActive = false;
      this.inFlight = false;
      this.snapshot = null;
      this.seed = +(root.dataset.seed || (group && group.seed) || 1);
      this.speed = root.dataset.speed || "1";
      this.overlayOn = root.dataset.overlay === "on";
      // GameWindow state: the smoothed (min, mean, max) and the 128x128 RGB field
      this.fieldRange = null;
      this.fieldRgb = null;
      this.min = root.dataset.hud === "min";
      this.id = -1;
      this.values = [];
            this.metrics = { bot: this.kind, seed: this.seed, gameFrames: 0, simMs: 0, mainMs: 0, workerMs: 0, ticks: 0 };
      this.root.__dodgeMetrics = this.metrics;
      this.build();
    }

    build() {
      const r = this.root;
      r.textContent = "";
      const top = el("div", "live-hud", r);
      el("span", "live-name", top, NAMES[this.kind]);
      this.hudFrames = el("span", "", top);
      if (!this.min) this.hudScore = el("span", "", top);
      this.hudCost = el("span", "", top);
      const screen = el("div", "live-screen", r);
      this.game = el("canvas", "game", screen);
      this.game.width = 128;
      this.game.height = 128;
      this.ov = el("canvas", "ov", screen);
      this.ov.width = 512;
      this.ov.height = 512;
      this.banner = el("div", "live-banner", screen);
      this.banner.hidden = true;
      this.ctx = this.game.getContext("2d");
      this.img = this.ctx.createImageData(128, 128);
      this.octx = this.ov.getContext("2d");
      if (r.dataset.controls !== "none") this.controls(el("div", "live-ctl", r));
      if (!this.min && this.kind !== "human" && this.kind !== "random") {
        const lower = el("div", "", r);
        lower.style.cssText = "display:flex; gap:18px; align-items:center;";
        this.compass = el("div", "compass", lower);
        this.compass.title = this.kind === "cnn" ? "π(a | s)" : "Relative score of each move";
        this.cells = COMPASS.map(a => el("span", "", this.compass, GLYPH[a]));
        if (this.kind === "cnn") {
          const box = el("div", "", lower);
          box.style.cssText = "flex:1; min-width:0; display:grid; gap:4px;";
          this.hudValue = el("span", "live-hud", box);
          this.spark = el("canvas", "spark", box);
          this.spark.width = 300;
          this.spark.height = 46;
        }
      }
    }

    controls(bar) {
      const btn = (label, fn, title) => {
        const b = el("button", "", bar, label);
        b.type = "button";
        if (title) b.title = title;
        b.addEventListener("click", fn);
        return b;
      };
      btn("−", () => this.restart(this.seed - 1), "Previous seed");
      this.seedLabel = el("span", "seed live-hud", bar);
      btn("+", () => this.restart(this.seed + 1), "Next seed");
      btn("↻", () => this.restart(this.seed), "Restart this seed");
      speedSelect(bar, this.speed, v => { this.speed = v; });
      if (this.root.dataset.overlay) {
        const ob = btn("overlay", () => {
          this.overlayOn = !this.overlayOn;
          ob.setAttribute("aria-pressed", String(this.overlayOn));
        }, "Show the policy's internals");
        ob.setAttribute("aria-pressed", String(this.overlayOn));
      }
    }

    // display.py GameWindow.set_field, line for line, in numpy's float32
    // arithmetic (a float32 array against a Python float stays float32).
    setField(field, rows, columns, smoothing = 0.1) {
      if (field == null) {
        this.fieldRgb = null;
        return;
      }
      const n = rows * columns;
      let lo = Infinity;
      let hi = -Infinity;
      for (let i = 0; i < n; i++) { if (field[i] < lo) lo = field[i]; if (field[i] > hi) hi = field[i]; }
      const current = [lo, f32(pairwise(field, 0, n) / n), hi];
      if (this.fieldRange == null) this.fieldRange = current;
      else this.fieldRange = this.fieldRange.map((previous, k) => previous + smoothing * (current[k] - previous));
      const [low, middle, high] = this.fieldRange;
      const low32 = f32(low);
      const middle32 = f32(middle);
      const belowSpan = f32(Math.max(middle - low, 1e-6));
      const aboveSpan = f32(Math.max(high - middle, 1e-6));
      // colorize(values, 0.0, 1.0): index = clip(v * 255, 0, 255) truncated
      const index = new Uint8Array(n);
      for (let i = 0; i < n; i++) {
        const v = field[i];
        const t = v < middle32
          ? f32(f32(0.5 * f32(v - low32)) / belowSpan)
          : f32(0.5 + f32(f32(0.5 * f32(v - middle32)) / aboveSpan));
        index[i] = Math.trunc(Math.min(Math.max(f32(t * 255), 0), 255));
      }
      // nearest neighbour to 128 x 128: rows = arange(128) * rows // 128
      const rgb = this.fieldRgb || new Uint8Array(128 * 128 * 3);
      for (let y = 0; y < 128; y++) {
        const r = Math.floor(y * rows / 128);
        for (let x = 0; x < 128; x++) {
          const c = 3 * index[r * columns + Math.floor(x * columns / 128)];
          const o = 3 * (y * 128 + x);
          rgb[o] = VIRIDIS[c];
          rgb[o + 1] = VIRIDIS[c + 1];
          rgb[o + 2] = VIRIDIS[c + 2];
        }
      }
      this.fieldRgb = rgb;
    }

    start() {
      this.stop();
      if (this.workerBacked) {
        this.workerActive = true;
        this.dead = false;
        this.deadFor = 0;
        this.cost = null;
        this.rate = 0;
        this.metrics = { bot: this.kind, seed: this.seed, gameFrames: 0, simMs: 0, mainMs: 0, workerMs: 0, ticks: 0 };
        this.root.__dodgeMetrics = this.metrics;
        this.inFlight = false;
        this.snapshot = null;
        if (!this.worker && workerLimit > 0) {
          this.worker = new Worker(workerUrl);
          this.worker.onmessage = ({ data }) => {
            if (data.type === "ready") {
              this.workerReady = true;
              if (this.workerStarting && this.workerActive) this.worker.postMessage({ type: "start", seed: this.seed });
              this.workerStarting = false;
              return;
            }
            if (data.type !== "frame") return;
            this.inFlight = false;
            this.snapshot = data;
            this.dead = data.info[2] === 1;
            this.cost = data.frames ? data.mainMs / data.frames : this.cost;
            this.rate = data.frames;
            this.metrics.gameFrames += data.frames;
            this.metrics.simMs += data.simMs;
            this.metrics.workerMs += data.mainMs;
            this.metrics.ticks++;
            const drawAt = performance.now();
            this.draw();
            const drawMs = performance.now() - drawAt;
            this.metrics.mainMs += drawMs;
            this.metrics.last = { frames: data.frames, simMs: data.simMs, workerMs: data.mainMs, mainMs: drawMs };
          };
          this.worker.onerror = e => console.error("belief worker", e.message);
          const workerWasm = Uint8Array.from(atob(WASM_B64), c => c.charCodeAt(0));
          this.worker.postMessage({ type: "init", wasm: workerWasm }, [workerWasm.buffer]);
        }
        if (this.workerReady) this.worker.postMessage({ type: "start", seed: this.seed });
        else this.workerStarting = true;
        if (this.seedLabel) this.seedLabel.textContent = "seed " + this.seed;
        return;
      }
      if (!wasm) return;
      this.id = wasm.sim_create(this.bot, this.seed >>> 0, 3, 1, 1);
      this.dead = false;
      this.deadFor = 0;
      this.cost = null;
      this.rate = 0;
      this.values = [];
      this.acc = 0;
      this.metrics = { bot: this.kind, seed: this.seed, gameFrames: 0, simMs: 0, mainMs: 0, ticks: 0 };
      this.root.__dodgeMetrics = this.metrics;
      this.banner.hidden = true;
      if (this.seedLabel) this.seedLabel.textContent = "seed " + this.seed;
      this.draw();
    }

    restart(seed) {
      this.seed = Math.max(1, seed | 0);
      this.start();
    }

    stop() {
      if (this.workerBacked) {
        this.workerActive = false;
        if (this.worker && this.workerReady) this.worker.postMessage({ type: "stop" });
        this.snapshot = null;
        this.inFlight = false;
        return;
      }
      if (wasm && this.id >= 0) wasm.sim_destroy(this.id);
      this.id = -1;
    }

    currentSpeed() {
      return this.group ? this.group.speed : this.speed;
    }

    tick(budget) {
      if (this.workerBacked) {
        if (!this.workerReady || this.inFlight || this.dead || !this.snapshot) return;
        this.inFlight = true;
        this.worker.postMessage({ type: "tick", budget, speed: this.currentSpeed(), mask: 0 });
        return;
      }
      if (this.id < 0) return;
      if (this.dead) {
        if (++this.deadFor > 150 && !this.group) this.restart(this.seed + 1);
        return;
      }
      const speed = this.currentSpeed();
      const mask = this.kind === "human" ? humanMask() : 0;
      const t0 = performance.now();
      let n = 0;
      let simMs = 0;
      if (speed === "max") {
        while (performance.now() - t0 < budget) {
          n++;
          const stepAt = performance.now();
          const dead = wasm.sim_step(this.id, mask, 1);
          simMs += performance.now() - stepAt;
          if (dead) { this.dead = true; break; }
        }
      } else {
        this.acc += +speed;
        while (this.acc >= 1) {
          this.acc -= 1;
          n++;
          const stepAt = performance.now();
          const dead = wasm.sim_step(this.id, mask, 1);
          simMs += performance.now() - stepAt;
          if (dead) { this.dead = true; break; }
          if (performance.now() - t0 > budget) { this.acc = 0; break; }
        }
      }
      const simDone = performance.now();
      if (n > 0) {
        const per = (performance.now() - t0) / n;
        this.cost = this.cost == null ? per : this.cost * 0.9 + per * 0.1;
        this.rate = n;
      }
      this.draw();
      this.metrics.gameFrames += n;
      this.metrics.simMs += simMs;
      this.metrics.mainMs += performance.now() - t0;
      this.metrics.ticks++;
      this.metrics.last = { frames: n, simMs, mainMs: performance.now() - t0, drawMs: performance.now() - simDone };
    }

    draw() {
      if (this.workerBacked ? !this.snapshot : this.id < 0) return;
      // slice 0, the nearest future: what watch_ppo.py draws (field(...)[0, 0])
      const dims = this.workerBacked ? 0 : (this.overlayOn || this.compass ? wasm.sim_inspect(this.id, 0) : 0);
      const w = Math.floor(dims / 65536);
      const h = dims % 65536;
      if (this.overlayOn && w && h) {
        this.setField(new Float32Array(wasm.memory.buffer, wasm.sim_overlay(this.id), w * h), h, w);
      } else {
        this.setField(null);
      }
      // GameWindow.compose: palette lookup, then the field on background pixels
      const px = this.workerBacked ? this.snapshot.pixels : new Uint8Array(wasm.memory.buffer, wasm.sim_render(this.id), 16384);
      const d = this.img.data;
      const field = this.fieldRgb;
      for (let i = 0; i < 16384; i++) {
        if (field && px[i] === BACKGROUND_INDEX) {
          d[4 * i] = field[3 * i];
          d[4 * i + 1] = field[3 * i + 1];
          d[4 * i + 2] = field[3 * i + 2];
        } else {
          const c = PAL[px[i] & 15];
          d[4 * i] = c[0];
          d[4 * i + 1] = c[1];
          d[4 * i + 2] = c[2];
        }
        d[4 * i + 3] = 255;
      }
      this.ctx.putImageData(this.img, 0, 0);
      // views are re-made after every call: memory can grow and detach them
      const info = this.workerBacked ? this.snapshot.info : new Float64Array(wasm.memory.buffer, wasm.sim_info(this.id), 16);
      const frames = info[0];
      this.hudFrames.innerHTML = `<b>${frames.toLocaleString("en-US")}</b> frames · ${(frames / 60).toFixed(1)} s`;
      if (this.hudScore) this.hudScore.innerHTML = `score <b>${Math.round(info[1])}</b>`;
      if (this.cost != null && this.kind !== "human") {
        const speed = this.currentSpeed();
        const slow = speed !== "max" && this.rate < +speed;
        this.hudCost.innerHTML = `<b>${this.cost < 1 ? this.cost.toFixed(2) : this.cost.toFixed(1)}</b> ms/frame` + (slow || this.cost > 16.7 ? " · below real time" : "");
      }
      const o = this.octx;
      o.clearRect(0, 0, 512, 512);
      const k = 512 / 128;
      if (this.overlayOn && dims) {
        const n = wasm.sim_path_len(this.id);
        if (n > 1) {
          const p = new Float32Array(wasm.memory.buffer, wasm.sim_path(this.id), 2 * n);
          o.strokeStyle = "#fff1e8";
          o.lineWidth = 3;
          o.beginPath();
          for (let i = 0; i < n; i++) {
            const x = p[2 * i] * k;
            const y = p[2 * i + 1] * k;
            if (i) o.lineTo(x, y); else o.moveTo(x, y);
          }
          o.stroke();
        }
        const info2 = this.workerBacked ? info : new Float64Array(wasm.memory.buffer, wasm.sim_info(this.id), 16);
        if ((this.kind === "lookahead" || this.kind === "landscape") && info2[10]) {
          const gx = info2[10] * k;
          const gy = info2[11] * k;
          o.strokeStyle = "#29adff";
          o.lineWidth = 3;
          o.beginPath();
          o.moveTo(gx - 14, gy); o.lineTo(gx + 14, gy);
          o.moveTo(gx, gy - 14); o.lineTo(gx, gy + 14);
          o.stroke();
        }
      }
      if (this.compass) {
        const s = this.workerBacked ? this.snapshot.scores : new Float32Array(wasm.memory.buffer, wasm.sim_scores(this.id), 9);
        const finite = Array.from(s).filter(Number.isFinite);
        const lo = Math.min(...finite);
        const hi = Math.max(...finite);
        const chosen = new Float64Array(wasm.memory.buffer, wasm.sim_info(this.id), 16)[4];
        COMPASS.forEach((a, i) => {
          const cell = this.cells[i];
          let t = 0;
          if (this.kind === "cnn") t = s[a];
          else if (finite.length) t = (s[a] - lo) / ((hi - lo) || 1);
          if (!Number.isFinite(t)) t = 0;
          cell.style.background = `rgba(255, 163, 0, ${(0.08 + 0.8 * t).toFixed(3)})`;
          cell.textContent = this.kind === "cnn" ? (s[a] >= 0.995 ? "1.0" : s[a].toFixed(2).replace(/^0/, "")) : GLYPH[a];
          cell.classList.toggle("on", a === chosen);
        });
      }
      if (this.spark) {
        const val = (this.workerBacked ? info : new Float64Array(wasm.memory.buffer, wasm.sim_info(this.id), 16))[5];
        if (Number.isFinite(val)) {
          this.values.push(val);
          if (this.values.length > 300) this.values.shift();
        }
        this.hudValue.innerHTML = `V(s) <b>${Number.isFinite(val) ? val.toFixed(2) : "–"}</b>`;
        const c = this.spark.getContext("2d");
        const W = 300;
        const H = 46;
        c.clearRect(0, 0, W, H);
        if (this.values.length > 1) {
          const lo = Math.min(...this.values);
          const hi = Math.max(...this.values);
          c.strokeStyle = "#29adff";
          c.lineWidth = 2;
          c.beginPath();
          this.values.forEach((v, i) => {
            const x = i / 299 * W;
            const y = H - 4 - (v - lo) / ((hi - lo) || 1) * (H - 8);
            if (i) c.lineTo(x, y); else c.moveTo(x, y);
          });
          c.stroke();
        }
      }
      if (this.dead) {
        const cause = CAUSES[(this.workerBacked ? info : new Float64Array(wasm.memory.buffer, wasm.sim_info(this.id), 16))[3]] || "unknown";
        this.banner.hidden = false;
        this.banner.textContent = `Hit by ${cause} at ${frames.toLocaleString("en-US")} frames` + (this.group ? "" : " · next seed shortly");
      }
    }
  }

  class Group {
    constructor(root) {
      this.root = root;
      this.seed = +(root.dataset.seed || 1);
      this.speed = root.dataset.speed || "1";
      this.lives = Array.from(root.querySelectorAll(".live")).map(e => new Live(e, this));
      const bar = root.querySelector(".group-ctl");
      bar.classList.add("live-ctl");
      const btn = (label, fn, title) => {
        const b = el("button", "", bar, label);
        b.type = "button";
        b.title = title;
        b.addEventListener("click", fn);
        return b;
      };
      btn("−", () => this.restart(this.seed - 1), "Previous seed");
      this.label = el("span", "seed live-hud", bar);
      btn("+", () => this.restart(this.seed + 1), "Next seed");
      btn("↻ restart", () => this.restart(this.seed), "Restart every game on this seed");
      speedSelect(bar, this.speed, v => { this.speed = v; });
      el("span", "live-hud", bar, "hard · patterns · powerups");
    }
    restart(seed) {
      this.seed = Math.max(1, seed | 0);
      this.label.textContent = "seed " + this.seed;
      for (const l of this.lives) { l.seed = this.seed; l.start(); }
    }
    start() { this.restart(this.seed); }
    stop() { this.lives.forEach(l => l.stop()); }
  }

  const bySlide = new Map();
  function widgets(slide) {
    if (!bySlide.has(slide)) {
      const groups = Array.from(slide.querySelectorAll(".live-group")).map(g => new Group(g));
      const solo = Array.from(slide.querySelectorAll(".live")).filter(e => !e.closest(".live-group")).map(e => new Live(e, null));
      bySlide.set(slide, { groups, solo, all: groups.flatMap(g => g.lives).concat(solo) });
    }
    return bySlide.get(slide);
  }

  let active = null;
  let human = false;
  async function activate(slide) {
    await ready;
    if (active) {
      active.groups.forEach(g => g.stop());
      active.solo.forEach(l => l.stop());
    }
    active = null;
    human = !!(slide && slide.dataset.human);
    keys.clear();
    if (!slide || !wasm) return;
    const w = widgets(slide);
    if (!w.all.length) return;
    w.groups.forEach(g => g.start());
    w.solo.forEach(l => l.start());
    active = w;
  }

  function frame() {
    window.__DODGE_RAF_COUNT = (window.__DODGE_RAF_COUNT || 0) + 1;
    if (active && !document.hidden) {
      const budget = Math.max(4, 14 / active.all.length);
      for (const l of active.all) l.tick(budget);
    }
    requestAnimationFrame(frame);
  }
  if (!reduced) requestAnimationFrame(frame);
  else document.addEventListener("click", () => { if (active) for (const l of active.all) l.tick(16); });

  // On the human slide the game owns the arrow keys; Page Up/Down still navigate.
  const GAME_KEYS = new Set(["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "a", "d", "w", "s", "r", " "]);
  const norm = e => (e.key.length === 1 ? e.key.toLowerCase() : e.key);
  window.addEventListener("keydown", e => {
    const k = norm(e);
    if (!human || !GAME_KEYS.has(k)) return;
    e.preventDefault();
    e.stopPropagation();
    if (k === "r" && active) active.groups.forEach(g => g.restart(g.seed));
    else keys.add(k);
  }, true);
  window.addEventListener("keyup", e => {
    const k = norm(e);
    keys.delete(k);
    if (human && GAME_KEYS.has(k)) { e.preventDefault(); e.stopPropagation(); }
  }, true);

  const hook = () => {
    Reveal.on("slidechanged", ev => activate(ev.currentSlide));
    activate(Reveal.getCurrentSlide());
  };
  if (Reveal.isReady()) hook(); else Reveal.on("ready", hook);
})();
