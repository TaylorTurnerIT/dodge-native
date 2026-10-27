import hashlib, json, os, sys
R = '/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/'
P = R + 'postovernight-long-D2-boundary-prepare-r9/'
def h(p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()
inputs = {}
for n in ('parent-frozen-pins.json','lifecycle.py','long_d2_executor.py','long_d2.py','synthetic.py','fixture_guards.py','os_checks.py','parent-result-r9.json'):
    inputs[P + n] = h(P + n)
C = P + 'attempts/attempt-03-focused-OS/cases/post-gate-persistent-mutation/'
for n in ('observed-command.json','execution/acceptance-receipt.json','campaign/inner-failure.json','campaign/worker.stderr.log','outer-events.jsonl','inner-events.jsonl','worker-events.jsonl','options.json'):
    inputs[C + n] = h(C + n)
inputs[R + 'postovernight-long-D2-boundary-startup-reap-diagnosis-sonnet-r1/dgram_close_probe.out.json'] = h(R + 'postovernight-long-D2-boundary-startup-reap-diagnosis-sonnet-r1/dgram_close_probe.out.json')
prot = '/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r6.json'
inputs[prot] = h(prot)
exp = {'long_d2.py':'288fdec9d013c3506846c17f4a43f4b5252822e983fa06231451a6487d84d18e','long_d2_executor.py':'fd603a1c1a4722043333d6587d1e1e731778e8c0bf8bcbac7e6ad68bfd276474','lifecycle.py':'aab36d678526b6fbd4eecbe1493ad3511365f00064a91d459b85834eaf3e752b'}
checks = {k: inputs[P + k] == v for k, v in exp.items()}
checks['protocol_r6'] = inputs[prot] == '96c170a5adb37829c2a8530d13b85d1d9c5f983a2b3582263893aa470b1ba3a4'
json.dump(dict(inputs=inputs, pin_checks=checks, note='parent-frozen-pins.json internal contents not re-parsed beyond controller/executor/lifecycle/protocol hash match'), open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'input-hashes.json'), 'w'), indent=1, sort_keys=True)
print(checks)
