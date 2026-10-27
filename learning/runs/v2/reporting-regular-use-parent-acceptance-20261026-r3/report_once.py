"""Read-only report of two exact parent-audited D2 inputs, with provenance."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
TOOL=ROOT/'learning/runs/v2/reporting-hardening-luna-20261026-r3/reporting_preflight.py'
EXPECTED_TOOL='aa718d322cb7c0163974ff3feaf11199e3b3a715f973d11753d17f16e51498bf'
INPUTS=[('BEST REFERENCE',ROOT/'learning/runs/v2/D2-gradient-alignment-20261025-r2/development-000180.json','2456bef85e7203d60496a6600631613a7dbc2987467d63d467dfec048f3d5680',180),('LATEST',ROOT/'learning/runs/v2/D2-continuation-20261025-r2/development-000252.json','f6f5dd73f1f3e4537f6646ea2c6726932569d88f26ca85d5b0eeb82384274614',252)]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(TOOL)==EXPECTED_TOOL
sys.path.insert(0,str(TOOL.parent));import reporting_preflight as report
assert Path(report.__file__).resolve()==TOOL
records=[]
for label,path,digest,phase in INPUTS:
 assert path.is_absolute() and sha(path)==digest
 data=json.loads(path.read_text());ev=data['evaluation']
 assert ev['stage']=='D2' and data['phase_update']==phase
 assert set(ev['death_causes'])<=set(report.ALL_CAUSES)
 if 'performance' in data:assert isinstance(data['performance'],dict)
 record=report.summarize_evaluation(path)
 records.append({'role':label,'path':str(path),'sha256':digest,'phase':phase,'canonical':record['summary'],'deaths':record['deaths']})
text=report.markdown_report(INPUTS[0][1],INPUTS[1][1])
for _,path,digest,_ in INPUTS:assert sha(path)==digest
assert sha(TOOL)==EXPECTED_TOOL
OWN=Path(__file__).resolve().parent
with (OWN/'report.md').open('x') as f:f.write(text+'\n')
with (OWN/'report-provenance.json').open('x') as f:json.dump({'tool':str(TOOL),'tool_sha256':EXPECTED_TOOL,'inputs':records,'report_sha256':sha(OWN/'report.md'),'scope':'Exact parent-audited D2 evaluation reporting only; no checkpoint-weight or execution authority validation.'},f,indent=2,sort_keys=True);f.write('\n')
print(text)
