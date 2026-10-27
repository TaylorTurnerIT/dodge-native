import json
from pathlib import Path

base = Path(__file__).resolve().parent.parent
campaign = base.with_name('postovernight-long-D2-campaign-r2')
for name in ('long-worker-result.json', 'inner-failure.json', 'checkpoint-index.json'):
    value = json.loads((campaign / name).read_text())
    print(name)
    if isinstance(value, dict):
        print(json.dumps({key: item if not isinstance(item, (dict, list)) else
            {'type': type(item).__name__, 'length': len(item),
             'keys': list(item) if isinstance(item, dict) else None}
            for key, item in value.items()}, sort_keys=True))
        for key in ('resource_summary', 'resources', 'worker_guard', 'guard_summary',
                    'first_global_failure', 'first_local_failure'):
            if key in value:
                print(key, json.dumps(value[key])[:4000])
    else:
        print(type(value).__name__, len(value))
