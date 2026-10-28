"""Read-only progress reporter for this single screen."""
import argparse,json,time
from pathlib import Path
import binding as b

def progress():
    p=b.protocol();out=Path(p['attempt_claim_path']).parent/'worker-output'
    result={'launch_marker_present':Path(p['launch_marker_path']).exists(),'output_present':out.is_dir()}
    counts={'constructors':0,'completed':0};events=out/'events.jsonl'
    if events.is_file():
        with events.open() as f:
            for line in f:
                try:
                    e=json.loads(line)
                    if e['kind']=='constructor':counts['constructors']+=1
                    elif e['kind']=='completed':counts['completed']+=1
                except (ValueError,KeyError):break
    result.update(counts);result['fraction_complete']=counts['completed']/2048
    result['worker_result_present']=(out/'worker-result.json').is_file()
    result['parent_terminal_audit_present']=(b.HERE/'parent-terminal-audit.json').is_file()
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--watch',type=int,default=0);a=p.parse_args()
    for _ in range(max(1,min(20,20 if a.watch else 1))):
        print(json.dumps(progress(),sort_keys=True),flush=True)
        if not a.watch:break
        time.sleep(a.watch)
