import hashlib
import json
import sys
h = hashlib.sha256()
frames = games = 0
for line in sys.stdin:
    row = json.loads(line)
    if 'end' in row:
        games += 1
        item = {'end': row['end']}
    else:
        frames += 1
        item = {key: row[key] for key in ('s', 'f', 'a')}
    h.update((json.dumps(item, sort_keys=True, separators=(',', ':')) + '\n').encode())
print(f'games={games} frames={frames} action_sha256={h.hexdigest()}')
