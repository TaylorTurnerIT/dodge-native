"""Build a local, self-contained view of the unchanged priority list and P5 gate."""
import json
from pathlib import Path

out = Path(__file__).resolve().parent
data = {
    "plan": json.loads((out / "long-run-protocol-v5.json").read_text()),
    "audit": json.loads((out / "readiness-audit.json").read_text()),
    "priority": {"rows": json.loads((out.parent / "priority-runlist-parent-20261030-r4/priority-run-list-v4.json").read_text())["rows"]},
}
html = r'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
*{box-sizing:border-box}html,body{margin:0;background:transparent;color:var(--foreground,#1e293b);font:14px/1.5 var(--font-sans,system-ui,sans-serif)}p{margin:8px 0 14px}h2{margin:0 0 8px;font-size:22px}h3{margin:14px 0 5px;font-size:17px}.muted{color:var(--muted-foreground,#64748b)}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:16px 0}.card{border:1px solid var(--border,#ccd5df);border-radius:var(--radius,10px);padding:16px;margin:12px 0;background:var(--card,#f8fafc)}.stats .card{margin:0}.big{display:block;font-size:23px;font-weight:750}nav{display:flex;gap:7px;flex-wrap:wrap;margin:16px 0}button{font:inherit;padding:8px 12px;border:1px solid var(--border,#ccd5df);border-radius:7px;background:var(--card,#f8fafc);color:inherit;cursor:pointer}button[aria-pressed=true]{background:var(--primary,#2563a0);color:var(--primary-foreground,#fff)}.head{display:flex;justify-content:space-between;gap:16px}.head strong{font-size:16px}.cost{white-space:nowrap;font-variant-numeric:tabular-nums}summary{cursor:pointer;font-weight:650}li{margin:7px 0}.badge{font-size:12px;font-weight:700;color:var(--warning-foreground,#7b4e00)}footer{margin:18px 0 0;font-size:12px;color:var(--muted-foreground,#64748b)}@media(max-width:540px){.stats{grid-template-columns:1fr}.head{display:block}.cost{display:block;margin-top:4px}}
</style></head><body>
<h2>Tune, qualify, then run long</h2><p>Design registered. Runtime outcomes unobserved. No launch or seed-cohort opening authorized.</p>
<div class="stats"><div class="card"><span class="big">2 replicas</span>One frozen winning recipe</div><div class="card"><span class="big">28h50m</span>Long-run ceiling, entry separate</div><div class="card"><span class="big">3 looks</span>Without joint progress: plateau stop</div></div>
<nav aria-label="Plan sections"><button data-tab="long" aria-pressed="true">Long-run gate</button><button data-tab="readiness" aria-pressed="false">Pipeline blockers</button><button data-tab="Phase0" aria-pressed="false">Phase 0</button><button data-tab="Phase1" aria-pressed="false">Phase 1</button><button data-tab="Phase2" aria-pressed="false">Phase 2</button></nav><div id="view"></div>
<footer>Hard proposed ceilings, not forecasts. Separate 6 GiB RSS/MPS caps, AC guard and one MPS job remain. Every packet needs registration, review, resource qualification and Taylor's explicit go-ahead. S1-r1 failure and held lease remain preserved; S1-r2 is unlaunched. Official parent 324 unchanged.</footer>
<script>const D=__DATA__;
function time(s){return Math.floor(s/3600)+'h'+String(Math.round((s%3600)/60)).padStart(2,'0')+'m'}
function card(title,cost,body){return `<section class="card"><div class="head"><strong>${title}</strong><span class="cost">${cost}</span></div>${body}</section>`}
function render(tab){document.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.tab===tab)));let content='';
if(tab==='long'){
content=card('1 · Independent entry qualification','14h18m if all four missing',`<p>Two candidate + two prospective matched current-recipe trajectories. Equal exposure; fresh 1,024-seed cohort; 5 models,5,120 games including 420.</p><p>Each replica must improve Q1 and Mean. Aggregate paired-game bootstrap lower 95% bounds must exceed 0 for both. Two training seeds still give limited training-population evidence.</p><p class="muted">Only controls missing: 8h12m. Existing model-only endpoints cannot restore live games.</p>`);
content+=card('2 · Maximum additional exposure','18h20m',`<p>117,964,800 raw frames per replica; 9h work + 10m receipts each. Locked LR/entropy schedules; no manual rate drops.</p><p>Every-update full-state checkpoints and last5 weight averages. No resets at monitoring barriers; no automatic failure recovery.</p>`);
content+=card('3 · Six rotating development looks','6h18m',`<p>Two current + two incumbent models on the same new 1,024 seeds per look: 24,576 games. Fixed sampled K1 controller.</p><p>Joint progress needs both replicas' positive Q1/Mean differences and positive aggregate bootstrap lower 95% bounds. Three accepted looks without joint progress stop for plateau.</p><p class="muted">Compare on the same cohort; separate current-policy and best-so-far curves. Repeated looks are development, not confirmation.</p>`);
content+=card('4 · Independent final confirmation','4h12m',`<p>Lock latest raw 2 + averaged 2 + entry 2 + 420 before 2,048 new seeds: 14,336 games. Latest raw versus entry is primary.</p><p>No silent best-checkpoint substitution or promotion. Total requested evaluation seeds including entry: 9,216; 0 opened or reserved now.</p>`);
content+=`<details><summary>Stop rules, health and resource admission</summary><ul><li>Hard wall/resource/AC/finiteness stops override learning. Budget stop is not plateau.</li><li>Proposed collapse: both replicas' Q1 and Mean upper95% contrast bounds below0 versus current incumbents.</li><li>Proposed KL stop: final KL&gt;0.15 for 3 completed updates. Freeze and qualify before approval.</li><li>Numerical KL, entropy, EV, advantage scale, switch rate and clip fraction every update; preserve definedness.</li><li>Source/full-state/telemetry/evaluation isolation and disk/I/O qualification must pass; forecast with 20% margin inside caps.</li></ul></details>`;
}else if(tab==='readiness'){
content='<p>Source-only audit complete. Existing PPO computes many required metrics; the formal journal discards their numerical values.</p>';
const main=['live_state','formal_recovery','learning_rate','fixed_lr_guard','metric_retention','telemetry_successor','evaluation_rng','evaluation_cohort','training_stream','resource_guard'];
content+=D.audit.findings.filter(x=>main.includes(x.id)).map(x=>card(x.id.replaceAll('_',' '),x.status.replaceAll('_',' '),`<p>${x.observation}</p><details><summary>Required successor work</summary><p>${x.successor_requirement}</p><p class="muted">${x.source} · lines ${x.lines.join(', ')}</p></details>`)).join('');
}else{
const rows=D.priority.rows.filter(x=>x.phase===tab);content=`<p class="muted">${rows.length} unchanged P4 packets. ${tab==='Phase0'?'S0 complete. Only A1/S1-r2 has a source-reviewed launch package; explicit successor approval still pending.':'Conditional reservations; two independent training seeds per arm. Separate evaluation budgets shown below.'}</p>`;
content+=rows.map(x=>card(x.id+' · '+x.name,time(x.total_ceiling_seconds)+(tab==='Phase0'?' total':' training / qualification'),`<p>${x.training_trajectories?x.training_trajectories+' trajectories ×'+x.raw_frames_per_training_trajectory.toLocaleString()+' raw frames each.':x.total_games||x.new_games?(x.total_games||x.new_games).toLocaleString()+' games on existing seeds.':(x.disposable_updates||0)+' disposable updates / source qualification.'}</p>${x.evaluation_games?'<p>Evaluation:'+x.evaluation_games.toLocaleString()+' games;'+time(x.evaluation_work_cap_seconds+x.evaluation_receipt_reserve_seconds)+' separate ceiling.</p>':''}<details><summary>Prediction and dependencies</summary><p>${x.prediction}</p><ul>${x.dependencies.map(y=>'<li>'+y+'</li>').join('')}</ul></details>`)).join('');
}
document.getElementById('view').innerHTML=content;
}
document.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>render(b.dataset.tab)));
for(const [phase,n] of [['Phase0',8],['Phase1',9],['Phase2',10]]){render(phase);if(document.querySelectorAll('#view section').length!==n)throw Error('Row coverage '+phase)}
render('readiness');if(document.querySelectorAll('#view section').length!==10)throw Error('Readiness coverage');render('long');
if(D.plan.combined_long_run_ceiling_seconds!==103800)throw Error('Budget drift');
requestAnimationFrame(()=>console.log(JSON.stringify({tabs_checked:5,priority_packets:27,long_run_seconds:103800,horizontal_overflow:document.documentElement.scrollWidth>innerWidth})));
</script></body></html>'''
html = html.replace('__DATA__', json.dumps(data, separators=(',', ':')).replace('</', '<\\/'))
(out / 'long-run-gate.html').write_text(html)
print('Built long-run-gate.html')
