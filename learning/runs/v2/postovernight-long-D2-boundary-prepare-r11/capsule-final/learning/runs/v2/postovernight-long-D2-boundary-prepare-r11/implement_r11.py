"""One preparation transform of exact r10 bytes. Never a runtime launcher."""
from pathlib import Path
import hashlib,json
H=Path(__file__).resolve().parent
p=H/'long_d2_executor.py';s=p.read_text()
marker='    def monitor(self):\n'
new='''    def kill_due(self,role):
        """Read the current shared window; only actual validated waits release
        a known supervisor before the existing latest eligibility cutpoint."""
        now=time.monotonic();latest=self.pool.until-.5
        if now<min(self.pool.first+5,latest):return None
        if role!='supervisor':return 'original_cutpoint'
        if now>=latest:return 'latest_bound'
        supervisor=self.groups.get('supervisor',{})
        if self.worker_wait is not None:
            owned.validate_report(self.worker_wait,self.groups.get('worker',{}).get('pid'),
                                  supervisor.get('pid'),self.t0,now,before=self.pool.until)
            return 'validated_worker_wait'
        if self.child is not None and self.child.report is not None:
            owned.validate_report(self.child.report,supervisor.get('pid'),os.getpid(),
                                  self.t0,now,before=self.pool.until)
            c.require(self.child.report['pid']==self.child.process.pid,
                      'Supervisor direct observation source differs')
            return 'supervisor_reaped'
        return None

'''
assert s.count(marker)==1;s=s.replace(marker,new+marker)
old='''                    if time.monotonic()>=min(self.pool.first+5,self.pool.until-.5):
                        self.monitor_duty('KILL_'+role,lambda record=record:owned.signal_once(record,signal.SIGKILL))
'''
new='''                    # Gate errors retain ORIGINAL eligibility, never immediate KILL.
                    due=['gate_error_original_cutpoint' if time.monotonic()>=min(self.pool.first+5,self.pool.until-.5) else None]
                    self.monitor_duty('KILL_gate_'+role,lambda role=role:due.__setitem__(0,self.kill_due(role)))
                    if due[0] is not None:
                        def escalate(role=role,record=record,reason=due[0]):
                            if not record.get('kill_sent') and not any(x.get('kind')=='escalation' and x['role']==role for x in self.events):
                                self.events.append(dict(kind='escalation',role=role,reason=reason,monotonic=time.monotonic()))
                            owned.signal_once(record,signal.SIGKILL)
                        self.monitor_duty('KILL_'+role,escalate)
'''
assert old in s;s=s.replace(old,new)
s=s.replace("if self.super_channel is not None and self.super_channel.sock.fileno()>=0:","if any(channel is not None and not getattr(channel,'peer_closed',False) for channel in (self.super_channel,self.worker_channel)):")
# Preserve stable endpoint order and all existing packet predicates verbatim.
start=s.index('        for channel in channels:\n',s.index('    def pump('))
end=s.index("        if self.worker_ready is not None",start)
loop=s[start:end]
body_start=loop.index('            try:\n')
body=loop[body_start:]
# Existing expected-reset handling remains inside this endpoint's isolated attempt.
wrapped='        first_error=None\n'+loop[:body_start]+'            try:\n'+''.join('    '+line if line.strip() else line for line in body.splitlines(True))+'''            except BaseException as endpoint_error:
                # Latch source failure before visiting the readable sibling. No
                # packet/send retry and no retirement from an empty datagram.
                if first_error is None:first_error=endpoint_error
                role='supervisor' if channel is self.super_channel else 'worker'
                def record_error(error=endpoint_error):raise error
                self.monitor_duty('IPC_'+role,record_error)
'''
s=s[:start]+wrapped+s[end:]
s=s.replace("        if self.worker_ready is not None and 'worker' in self.groups", "        if self.pool.until is None and self.worker_ready is not None and 'worker' in self.groups")
end=s.index('\n    def recover_registration_race',start)
s=s[:end]+"        if first_error is not None:raise first_error\n"+s[end:]
p.write_text(s)
# Proposal starts from exact CURRENT external r7, not a historical envelope.
root=H.parents[3];old=(root/'learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r7.json').read_text()
old=old.replace('postovernight-long-D2-boundary-prepare-r10','postovernight-long-D2-boundary-prepare-r11').replace('postovernight-long-D2-r2-protocol-r7.json','postovernight-long-D2-r2-protocol-r8.json')
proposal=json.loads(old)
proposal['r11_qualified_repairs']={
 'staged_owned_escalation':'Worker TERM immediate and KILL at current min(first+5,until-.5); supervisor TERM immediate. At that original eligibility, supervisor KILL requires validated actual worker_wait or matching actual direct-reaped supervisor leader; otherwise eligible until-.5. child None and absent worker registration prove neither. Recompute each tick; gate exception fallback uses original eligibility. One reason and actual signal-attempt timestamp per role; cooperative scheduling, no exact signal-at-L guarantee.',
 'endpoint_isolation':'Stable supervisor then worker readiness order. Unexpected receive, packet validation and ACK-send errors remain fatal and source-stamped per endpoint before continuing to an already-readable sibling once under current absolute deadline. Retain valid earlier peer failure and ACK once; recompute deadline after each peer. No retry, transport change, blanket close relaxation, reaping from retirement, or recovery/start ACK after failed normal operation. Existing final drain remains until-.25; bounded deduplicated monitor diagnostics at most eight.'}
raw=json.dumps(proposal,sort_keys=True,indent=2)+'\n';(H/'protocol-r8-proposal.json').write_text(raw)
p=H/'long_d2.py';s=p.read_text().replace('postovernight-long-D2-boundary-prepare-r10','postovernight-long-D2-boundary-prepare-r11').replace('postovernight-long-D2-r2-protocol-r7.json','postovernight-long-D2-r2-protocol-r8.json')
s=s.replace('49b25af4181353cc6d31b03c3666475c37eb5a433b4038d4cc4076519420ebce',hashlib.sha256(raw.encode()).hexdigest());p.write_text(s)
for name in ('test_r7.py','test_r10.py'):
 p=H/name;s=p.read_text().replace('protocol-r7-proposal.json','protocol-r8-proposal.json')
 if name=='test_r10.py':
  s=s.replace("self.assertIsNone(x.pool.until);self.assertIsNone(x.worker_wait)","self.assertEqual((x.pool.first,x.pool.until),(100.,110.));self.assertIsNone(x.worker_wait)")
  # Escalation adds one bounded row per role outside the eight error diagnostics.
  s=s.replace('self.assertLessEqual(len(x.events),8)','self.assertLessEqual(sum(v.get(\'kind\')==\'monitor_error\' for v in x.events),8)')
  s=s.replace("sum(v['duty']=='IPC' for v in x.events)","sum(v.get('duty')=='IPC' for v in x.events)")
 p.write_text(s)
# Stage wrapper owns fresh source receipts, unchanged fixture precheck logic plus r11.
p=H/'unit_stage.py';s=p.read_text().replace("['test_r10','test_r7','test_repairs','test_boundary']","['test_r11','test_r10','test_r7','test_repairs','test_boundary']").replace('protocol-r7-proposal.json','protocol-r8-proposal.json')
s=s.replace("'test_r10.py','fixture_preconditions.py'","'test_r11.py','test_r10.py','fixture_preconditions.py'")
s=s.replace("    shutil.copytree(H/'r9-source',source/'r9-source')","    shutil.copytree(H/'r9-source',source/'r9-source')\n    shutil.copytree(H/'r10-source',source/'r10-source')")
p.write_text(s)
p=H/'run_unit_suite.py';s=p.read_text().replace('import test_r10','import test_r10\nimport test_r11').replace('(test_r10,test_r7,test_repairs,test_boundary)','(test_r11,test_r10,test_r7,test_repairs,test_boundary)');p.write_text(s)
print('r11 two-repair preparation written; no validation stage run')
