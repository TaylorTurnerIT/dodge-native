// Run the browser build under Node: same games as the native parity harness.
import { readFileSync } from "node:fs";
const bytes = readFileSync(new URL("../target/wasm32-unknown-unknown/release/dodge_web.wasm", import.meta.url));
const { instance } = await WebAssembly.instantiate(bytes, {});
const w = instance.exports;
console.log("imports:", WebAssembly.Module.imports(new WebAssembly.Module(bytes)).map(i => i.module + "." + i.name).join(", ") || "none");
const runs = [[3, 1, 18000, "CNN", 5548], [3, 3, 18000, "CNN", 1506], [2, 3, 18000, "SpaceBot", 5913], [6, 1, 18000, "Landscape", 613], [1, 1, 3000, "M0", null], [4, 1, 600, "Belief", null]];
for (const [bot, seed, cap, name, want] of runs) {
  const id = w.sim_create(bot, seed, 3, 1, 1);
  const t0 = performance.now();
  let frames = 0;
  while (frames < cap && !w.sim_step(id, 0, 1)) frames++;
  const ms = (performance.now() - t0) / Math.max(frames, 1);
  const info = new Float64Array(w.memory.buffer, w.sim_info(id), 16);
  console.log(`${name} seed ${seed}: survival ${info[0]}${want != null ? ` (native ${want})` : ""}, ${ms.toFixed(2)} ms/frame`);
  w.sim_destroy(id);
}
