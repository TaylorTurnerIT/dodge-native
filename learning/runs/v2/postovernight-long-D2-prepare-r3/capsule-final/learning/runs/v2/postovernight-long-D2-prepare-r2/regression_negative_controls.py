"""Kill exact retained r1 with new actual-supervisor publication regressions."""
from pathlib import Path
import os
import subprocess
import sys
import long_d2 as c

HERE=Path(__file__).resolve().parent
R1=HERE.parent/'postovernight-long-D2-prepare-r1/long_d2.py'
TESTS=['test_late_cancel_hash_real_guard_both_outcomes',
       'test_late_input_hash_real_guard_both_outcomes',
       'test_real_SIGINT_SIGTERM_outer_publication_alarm_exit']


def main():
    round_name=sys.argv[1]
    directory=HERE/('r1-regression-controls-'+round_name);directory.mkdir(exist_ok=False)
    c.require(c.sha(R1)=='62ece46ba9a59d3c116013580ce29875aa76eaceed59eb56480a804649c8ffca','Exact r1 changed')
    results=[]
    for test in TESTS:
        evidence=directory/test;evidence.mkdir()
        command=[sys.executable,'-B','-m','unittest','test_publication.PublicationTests.'+test,'-v']
        run=subprocess.run(command,cwd=HERE,capture_output=True,text=True,timeout=45,
                env=dict(os.environ,LONG_D2_TEST_SOURCE=str(R1),LONG_D2_PROBE_EVIDENCE=str(evidence),
                         PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(HERE/'tmp')))
        log=directory/(test+'.log');log.write_text(run.stdout+run.stderr)
        assertion=run.returncode!=0 and 'FAIL:' in run.stderr and 'AssertionError' in run.stderr
        api_error=any(x in run.stderr for x in ('ERROR:','ImportError','SyntaxError','AttributeError','TypeError'))
        results.append(dict(test=test,source=str(R1),source_sha256=c.sha(R1),command=command,
                            exit_code=run.returncode,assertion_failure=assertion,API_or_import_errors=api_error,
                            log=str(log.relative_to(HERE)),log_sha256=c.sha(log),killed=assertion and not api_error))
        print(test,results[-1]['killed'],flush=True)
    c.save(HERE/('r1-regression-control-receipt-'+round_name+'.json'),dict(
        count=len(results),all_killed=all(v['killed'] for v in results),cases=results,
        exact_r1_not_rewritten_or_import_adapted=True,source_sha256=c.sha(R1)))
    return 0 if all(v['killed'] for v in results) else 1


if __name__=='__main__':raise SystemExit(main())
