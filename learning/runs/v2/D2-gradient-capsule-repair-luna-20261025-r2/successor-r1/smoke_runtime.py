import json,sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from dodge_rl import identity, dev_eval
p=identity.read_protocol()
seeds=dev_eval.development_seeds()
assert len(seeds)==64
rows=[]
for seed in seeds:
    rows.append([int(seed), dev_eval.development_environment_config(int(seed), "D2")])
print(json.dumps({"protocol":p,"seeds":[int(x) for x in seeds],"rows":rows},sort_keys=True,separators=(",",":"),allow_nan=False))
