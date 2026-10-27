import json,sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from dodge_rl import identity, dev_eval
p=identity.read_protocol()
seeds=dev_eval.development_seeds()
assert len(seeds)==64
rows=[[int(seed), dev_eval.development_environment_config(int(seed), "D2")] for seed in seeds]
origins={"identity":str(Path(identity.__file__).resolve()),"dev_eval":str(Path(dev_eval.__file__).resolve())}
print(json.dumps({"protocol":p,"seeds":[int(x) for x in seeds],"rows":rows,"module_origins":origins},sort_keys=True,separators=(",",":"),allow_nan=False))
