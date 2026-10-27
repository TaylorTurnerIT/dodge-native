"""Build a self-contained dual replay from verified native palette captures."""
import base64
import hashlib
import json
from pathlib import Path

OWN = Path(__file__).resolve().parent
plan = json.loads((OWN / "plan.json").read_text())
result = json.loads((OWN / "result.json").read_text())
if result["status"] != "passed_exact_64_recorded_rows":
    raise ValueError("Capture did not match recorded evaluation")
clips = []
for clip in plan["clips"]:
    role = clip["role"]
    trace = json.loads((OWN / (role + ".trace.json")).read_text())
    clips.append({"role": role, "row": clip["row"], **trace,
                  "compressed": base64.b64encode((OWN / (role + ".palette.zlib")).read_bytes()).decode()})
html = r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dodge · average and best · checkpoint 348</title>
<style>
:root{color-scheme:dark;--background:#111318;--foreground:#e9edf3;--muted-foreground:#a0a9b8;--border:#303541;--primary:#9dd3fc;--font-sans:system-ui,sans-serif}
*{box-sizing:border-box}html,body{margin:0;background:transparent;color:var(--foreground);font:14px var(--font-sans)}
header{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:16px}header p{margin:0;color:var(--muted-foreground)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}h2{font-size:17px;font-weight:600;margin:0 0 5px}.meta{color:var(--muted-foreground);margin:0 0 10px;font-size:13px}
canvas{display:block;width:100%;height:auto;aspect-ratio:1;image-rendering:pixelated;background:#000;border-radius:8px}
.controls{display:flex;align-items:center;gap:8px;margin:10px 0}button,select{border:1px solid var(--border);background:transparent;color:inherit;border-radius:6px;padding:7px 10px;font:inherit;cursor:pointer}button:hover{border-color:var(--primary)}
input[type=range]{width:100%;accent-color:var(--primary);margin:4px 0}output{margin-left:auto;font-variant-numeric:tabular-nums;color:var(--muted-foreground);font-size:12px}.status{height:18px;color:var(--muted-foreground);font-size:12px;margin:5px 0 0}
footer{color:var(--muted-foreground);font-size:12px;margin-top:16px}@media(max-width:540px){.grid{grid-template-columns:1fr}header{align-items:flex-start}}
</style>
<header><p>Retained checkpoint 348 · D2 · real-time playback</p><button id="restart">Restart both</button></header><main class="grid" id="clips"></main>
<footer>Average = episode nearest the 3,098-frame mean. Best = longest of the same 64 games. Native palette; snapshots every four game frames.</footer>
<script>
const CLIPS=__CLIPS__;
const PALETTE=[[0,0,0],[29,43,83],[126,37,83],[0,135,81],[171,82,54],[95,87,79],[194,195,199],[255,241,232],[255,0,77],[255,163,0],[255,236,39],[0,228,54],[41,173,255],[131,118,156],[255,119,168],[255,204,170]];
const cause={normal_enemy:'normal enemy',static_pattern_rect:'static rectangle'};
const players=[];window.__replays={ready:false,error:null,players:[]};
async function makePlayer(c){
 const article=document.createElement('article');article.innerHTML=`<h2>${c.role==='average'?'Average run':'Best run'}</h2><p class="meta">${c.row.alive_frames.toLocaleString()} alive frames · ${(c.row.gameplay_frames/60).toFixed(1)} seconds · seed ${c.row.seed}</p><canvas width="128" height="128" aria-label="${c.role} run gameplay"></canvas><div class="controls"><button class="toggle" aria-label="Pause ${c.role}">Pause</button><select aria-label="${c.role} playback speed"><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option><option value="4">4×</option></select><output>Loading…</output></div><input aria-label="Seek ${c.role}" type="range" min="0" max="${c.frames.length-1}" value="0"><p class="status">Loading native capture…</p>`;
 document.querySelector('#clips').append(article);
 const bin=Uint8Array.from(atob(c.compressed),x=>x.charCodeAt(0));const raw=new Uint8Array(await new Response(new Blob([bin]).stream().pipeThrough(new DecompressionStream('deflate'))).arrayBuffer());
 if(raw.length!==c.frames.length*16384)throw Error('Capture dimensions differ');
 const canvas=article.querySelector('canvas'),ctx=canvas.getContext('2d'),pixels=ctx.createImageData(128,128),button=article.querySelector('.toggle'),speed=article.querySelector('select'),slider=article.querySelector('input'),clock=article.querySelector('output'),status=article.querySelector('.status');
 const p={role:c.role,index:0,playing:true,base:0,start:performance.now(),speed:1};window.__replays.players.push(p);players.push(p);
 function draw(i){p.index=Math.max(0,Math.min(c.frames.length-1,i));const off=p.index*16384;for(let j=0;j<16384;j++){const rgb=PALETTE[raw[off+j]],k=j*4;pixels.data[k]=rgb[0];pixels.data[k+1]=rgb[1];pixels.data[k+2]=rgb[2];pixels.data[k+3]=255}ctx.putImageData(pixels,0,0);slider.value=p.index;clock.textContent=`${(c.frames[p.index]/60).toFixed(1)} / ${(c.row.gameplay_frames/60).toFixed(1)} s`;status.textContent=p.index===c.frames.length-1?`Ended: ${cause[c.row.death_cause]||c.row.death_cause} · Score ${c.scores[p.index]}`:`Frame ${c.frames[p.index].toLocaleString()} · Score ${c.scores[p.index]}`;}
 function pause(){p.playing=false;button.textContent=p.index===c.frames.length-1?'Replay':'Play';button.setAttribute('aria-label',`Play ${c.role}`)}
 function play(){if(p.index===c.frames.length-1)draw(0);p.base=c.frames[p.index];p.start=performance.now();p.playing=true;button.textContent='Pause';button.setAttribute('aria-label',`Pause ${c.role}`)}
 p.restart=()=>{draw(0);play()};button.onclick=()=>p.playing?pause():play();slider.oninput=()=>{pause();draw(Number(slider.value))};speed.onchange=()=>{p.base=c.frames[p.index];p.start=performance.now();p.speed=Number(speed.value)};
 function tick(now){if(p.playing){const frame=p.base+(now-p.start)*.06*p.speed;let lo=0,hi=c.frames.length-1;while(lo<hi){const mid=Math.ceil((lo+hi)/2);if(c.frames[mid]<=frame)lo=mid;else hi=mid-1}if(lo!==p.index)draw(lo);if(frame>=c.frames[c.frames.length-1]){draw(c.frames.length-1);pause()}}requestAnimationFrame(tick)}
 draw(0);requestAnimationFrame(tick);return p;
}
document.querySelector('#restart').onclick=()=>players.forEach(p=>p.restart());
Promise.all(CLIPS.map(makePlayer)).then(()=>{window.__replays.ready=true;console.log('Replay captures decoded',players.length)}).catch(e=>{window.__replays.error=e.message;console.error(e);document.querySelectorAll('.status').forEach(e=>e.textContent='Playback error')});
</script></html>'''.replace('__CLIPS__', json.dumps(clips, separators=(',', ':')))
with (OWN / "index.html").open("x") as stream:
    stream.write(html)
print(json.dumps({"html_bytes":len(html.encode()),"sha256":hashlib.sha256(html.encode()).hexdigest(),"clips":2}))
