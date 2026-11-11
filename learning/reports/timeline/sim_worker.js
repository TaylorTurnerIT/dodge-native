// Belief-planner simulation worker. Its framebuffer and HUD arrays are
// transferred to the page so planner rollouts do not block slide navigation.
let wasm = null;
let sim = -1;
let acc = 0;
let dead = false;
let generation = 0;

async function init(bytes) {
  try {
    const { instance } = await WebAssembly.instantiate(bytes, {});
    wasm = instance.exports;
    postMessage({ type: "ready" });
  } catch (error) {
    postMessage({ type: "error", message: String(error) });
  }
}

function stop() {
  if (wasm && sim >= 0) wasm.sim_destroy(sim);
  sim = -1;
}

function snapshot(frames, simMs, mainMs) {
  const pixels = new Uint8Array(wasm.memory.buffer, wasm.sim_render(sim), 16384).slice();
  const info = new Float64Array(wasm.memory.buffer, wasm.sim_info(sim), 16).slice();
  const scores = new Float32Array(wasm.memory.buffer, wasm.sim_scores(sim), 9).slice();
  const dims = wasm.sim_inspect(sim, 0);
  const w = Math.floor(dims / 65536), h = dims % 65536;
  const field = w && h ? new Float32Array(wasm.memory.buffer, wasm.sim_overlay(sim), w * h).slice() : new Float32Array();
  const n = wasm.sim_path_len(sim);
  const path = n ? new Float32Array(wasm.memory.buffer, wasm.sim_path(sim), 2 * n).slice() : new Float32Array();
  postMessage({ type: "frame", generation, frames, simMs, mainMs, pixels, info, scores, field, width: w, height: h, path },
    [pixels.buffer, info.buffer, scores.buffer, field.buffer, path.buffer]);
}

onmessage = async ({ data }) => {
  if (data.type === "init") return init(data.wasm);
  if (data.type === "stop") return stop();
  if (data.type === "start") {
    stop();
    generation = data.generation;
    sim = wasm.sim_create(4, data.seed >>> 0, 3, 1, 1);
    acc = 0;
    dead = false;
    return snapshot(0, 0, 0);
  }
  if (data.type !== "tick" || sim < 0 || dead || data.generation !== generation) return;
  const t0 = performance.now();
  let frames = 0;
  let simMs = 0;
  if (data.speed === "max") {
    while (performance.now() - t0 < data.budget) {
      const stepAt = performance.now();
      dead = wasm.sim_step(sim, data.mask, 1);
      simMs += performance.now() - stepAt;
      frames++;
      if (dead) break;
    }
  } else {
    acc += +data.speed;
    while (acc >= 1) {
      acc -= 1;
      const stepAt = performance.now();
      dead = wasm.sim_step(sim, data.mask, 1);
      simMs += performance.now() - stepAt;
      frames++;
      if (dead || performance.now() - t0 > data.budget) { acc = 0; break; }
    }
  }
  snapshot(frames, simMs, performance.now() - t0);
};
