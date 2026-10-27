from pathlib import Path
p=Path(__file__).with_name('long_d2_executor.py');s=p.read_text()
s=s.replace('import processes as owned','import processes as owned\nimport boundary_integrity as integrity')
s=s.replace("              'protocol_sha256','config_sha256','identity_sha256','capsule_manifest_sha256'}", "              'protocol_sha256','config_sha256','identity_sha256','capsule_manifest_sha256',\n              'classification_sha256','reservation_sha256','class_manifest_hashes','class_counts','cache_policy','root_exclusions'}")
s=s.replace("'long_d2_executor_registration_v1'", "'long_d2_executor_registration_v2'")
s=s.replace("                    str(root/c.PROTOCOL_REL),str(root/p['config_path'])}", "                    str(root/c.PROTOCOL_REL),str(root/p['config_path']),\n                    str(root/c.PREPARE_REL/'classification.json')}")
s=s.replace("           'worker-verification.jsonl','worker-verification.manifest.json',\n",'')
s=s.replace("        c.require(name in fixed or re.fullmatch(checkpoint_pattern,name),", "        c.require(name in fixed or name in {'worker-verification.jsonl','worker-verification.manifest.json'} or re.fullmatch(checkpoint_pattern,name),")
s=s.replace("        c.require(0<=resources['maximum_sample_gap_seconds']<=.5\n                  and 0<=resources['maximum_full_input_gap_seconds']<=5, 'Observation gap invalid')", "        c.require(0<=resources['maximum_sample_gap_seconds']<=.5, 'Safety observation gap invalid')")
s=s.replace("    authority(True)\n    return dict(artifact_manifest_sha256", "    c.require(wr.get('integrity_summary') is not None, 'Mandatory worker integrity summary missing')\n    authority(True)\n    return dict(worker_integrity_summary=wr['integrity_summary'],artifact_manifest_sha256")
s=s.replace("        self.pool.fail(error,min(candidates))", "        primary, descriptor = c.observed_failure(error,self.guard,'outer')\n        if at is not None and at < descriptor['timestamp']:\n            descriptor = dict(timestamp=at,kind='peer_or_source_failure',outcome=c.failure_outcome(error),role='peer',timing_basis='explicit_source_timestamp',signal=None)\n        self.pool.fail(primary,descriptor['timestamp'],descriptor)")
s=s.replace("        c.require(time.monotonic()-self.guard.last_full<=5 and time.monotonic()-self.guard.last_sample<=.5,\n                  'Outer final observation age exceeded')", "        c.require(time.monotonic()-self.guard.last_sample<=.5, 'Outer safety observation age exceeded')")
s=s.replace("                    if self.guard.last_full is not None and now-self.guard.last_full>5:self.fail('Outer full-pin age')\n",'')
s=s.replace("                self.fail(value['reason'],float.fromhex(value['first_monotonic_hex']))", "                first=float.fromhex(value['first_monotonic_hex'])\n                self.pool.fail(value['reason'],first,value.get('descriptor'),peer=True)\n                self.latch.phase='FAILURE'")
s=s.replace("                    cleanup_until_monotonic_hex=self.pool.until.hex(),t0_monotonic_hex=self.t0.hex()),self.pool.until)", "                    cleanup_until_monotonic_hex=self.pool.until.hex(),t0_monotonic_hex=self.t0.hex(),descriptor=self.pool.first_global),self.pool.until)")
a=s.index('            def verify():',s.index('    def run(self):'));b=s.index('            self.guard=self.guard_factory',a)
s=s[:a]+'''            def verify():
                c.verify_files(self.registration['pins'])
                c.require(c.sha(REGISTRATION_PATH)==self.registration_digest, 'External registration changed')
                integrity.cache_check(self.registration['cache_policy'])
                return integrity.verify(self.context,c.ROOT)
'''+s[b:]
s=s.replace('            self.guard.start()','            self.registration_digest=c.sha(REGISTRATION_PATH)\n            self.guard.start()',1)
s=s.replace('            parent,child_socket=life.pair();gate_parent,gate_child=life.pair()', "            self.preflight=integrity.verify(self.context,c.ROOT,endpoint='preflight')\n            self.authority(False)\n            parent,child_socket=life.pair();gate_parent,gate_child=life.pair()")
s=s.replace("            code=inner['returncode']\n            result=dict(schema='long_d2_outer_acceptance_v1'", """            postflight=integrity.verify(self.context,c.ROOT,endpoint='postflight')
            summary=dict(schema='long_d2_compact_integrity_summary_v1',
                protocol_sha256=c.PROTOCOL_SHA256, config_sha256=c.CONFIG_SHA256,
                identity_sha256=self.registration['identity_sha256'], classification_sha256=self.registration['classification_sha256'],
                reservation_sha256=self.registration['reservation_sha256'], manifests=self.registration['class_manifest_hashes'],
                preflight=self.preflight,postflight=postflight,worker=bindings['worker_integrity_summary'],
                first_local_failure=self.pool.first_local,first_global_failure=self.pool.first_global)
            c.require(integrity.summary_valid(summary,self.registration),'Mandatory integrity summary differs')
            summary_path=receipt_path.parent/'integrity-summary.json'
            receipt_path.parent.mkdir(parents=False,exist_ok=True)
            c.save(summary_path,summary)
            bindings['integrity_summary_sha256']=c.sha(summary_path)
            bindings['integrity_summary_path']=str(summary_path)
            code=inner['returncode']
            result=dict(schema='long_d2_outer_acceptance_v2'""")
s=s.replace("                registration=self.registration,required_lease=lease,outer_resources=self.guard.receipt(),", "                registration=self.registration,registration_sha256=self.registration_digest,integrity_summary=summary,required_lease=lease,outer_resources=self.guard.receipt(),")
s=s.replace("            self.guard.persist_timing(receipt_path.parent/'outer-verification.jsonl',", "            c.optional_timing(self.guard,receipt_path.parent/'outer-verification.jsonl',")
s=s.replace("result=dict(schema='long_d2_outer_acceptance_v1',accepted=False", "result=dict(schema='long_d2_outer_acceptance_v2',accepted=False")
s=s.replace("                    cleanup_until_monotonic=self.pool.until,cleanup_complete=self.cleanup_complete,", "                    cleanup_until_monotonic=self.pool.until,cleanup_complete=self.cleanup_complete,\n                    first_local_failure=self.pool.first_local,first_global_failure=self.pool.first_global,")
s=s.replace("                if self.guard is not None:\n                    self.guard.persist_timing(receipt_path.parent/'outer-verification.jsonl',self.pool.until)\n                c.replace_json(receipt_path,result)", "                c.mandatory_failure(receipt_path,result,self.pool.until)\n                if self.guard is not None:\n                    c.optional_timing(self.guard,receipt_path.parent/'outer-verification.jsonl',self.pool.until)")
a=s.index('def accept_observed(');b=s.index('\ndef main():',a)
s=s[:a]+'''def accept_observed(receipt, raw_exit, elapsed_seconds, *, registration_sha256=None, summary_sha256=None):
    """Parent holds these digests and independently observes raw exit and wall.

    File checks are current actual bytes, not a manifest-only passing verdict.
    Missing parent pins, mandatory summary, ownership, or critical files reject.
    """
    try:
        if not (type(raw_exit) is int and raw_exit in (0,2) and type(elapsed_seconds) in (int,float)
                and math.isfinite(elapsed_seconds) and 0<=elapsed_seconds<=NORMAL_SECONDS
                and receipt.get('schema')=='long_d2_outer_acceptance_v2' and receipt.get('accepted') is True
                and receipt.get('expected_exit_code')==raw_exit and receipt.get('experiment_status')=='complete'
                and receipt.get('outcome')==('D2_progress_gate_passed' if raw_exit==0 else 'budget_closed_below_gate')
                and receipt.get('teacher_qualified') is False and receipt.get('training_parent_eligible') is False):
            return False
        registration=receipt['registration'];bindings=receipt['bindings'];summary=receipt['integrity_summary']
        c.require(registration_sha256 is not None and receipt['registration_sha256']==registration_sha256==c.sha(REGISTRATION_PATH), 'Parent registration digest missing/different')
        c.require(c.read_json(REGISTRATION_PATH)==registration,'Registration content differs')
        c.verify_files(registration['pins'])
        c.require(summary_sha256 is not None and bindings['integrity_summary_sha256']==summary_sha256==c.sha(bindings['integrity_summary_path']), 'Parent summary digest missing/different')
        c.require(c.read_json(bindings['integrity_summary_path'])==summary and integrity.summary_valid(summary,registration),'Mandatory summary differs')
        c.require(receipt['required_lease']==c.read_json(c.ORIGINAL_ROOT/c.PREPARE_REL/'required-lease.json'),'Required ownership/lease differs')
        c.require(set(receipt['ownership'])=={'supervisor','worker'} and all(v['new_session_verified'] and v['group_absent'] for v in receipt['ownership'].values()),'Ownership incomplete')
        output=Path(registration['output'])
        c.verify_files({str(output/k):v for k,v in bindings['artifacts'].items()})
        for name,key in (('artifact-manifest.json','artifact_manifest_sha256'),('long-run-result.json','run_result_sha256'),('finalization-result.json','terminal_sha256'),('long-worker-result.json','worker_result_sha256')):
            c.require(c.sha(output/name)==bindings[key],'Critical artifact differs: '+name)
        return True
    except (KeyError, TypeError, OSError, c.Stop):
        return False

'''+s[b:]
s=s.replace("    parser.add_argument('--registration',type=Path,default=REGISTRATION_PATH)", "    parser.add_argument('--registration',type=Path,default=REGISTRATION_PATH)\n    parser.add_argument('--registration-sha256',required=True)")
s=s.replace("    if args.command=='preflight':\n        registration", "    c.require(c.sha(args.registration)==args.registration_sha256, 'Parent launch registration digest differs')\n    if args.command=='preflight':\n        registration")
p.write_text(s)
