import os
import subprocess
import sys
import pytest
import time


def test_blocked_stdin_does_not_bypass_the_process_deadline():
    from lab.process_guard import bounded_run
    started=time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        bounded_run([sys.executable,'-c','import time; time.sleep(2)'],input='x'*2_000_000,timeout=.15)
    assert time.monotonic()-started<1.5


def test_large_input_and_output_can_flow_at_the_same_time():
    # Supervise the wrapper too: a regression must fail, not hang the test runner.
    code='''from lab.process_guard import bounded_run
import sys
child='import sys; sys.stdout.write("x"*100000); sys.stdout.flush(); print(len(sys.stdin.read()))'
result=bounded_run([sys.executable,'-c',child],input='y'*200000,timeout=2)
assert result.returncode==0 and result.stdout.replace('\\r\\n','\\n')=='x'*100000+'200000\\n'
'''
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=6)
    assert result.returncode==0,result.stderr


@pytest.mark.skipif(os.name!='nt',reason='Windows construction backend')
def test_bounded_process_returns_output_and_times_out():
    from lab.process_guard import bounded_run
    r=bounded_run([sys.executable,'-c','print("ok")'],timeout=3)
    assert r.returncode==0 and r.stdout.strip()=='ok'
    with pytest.raises(subprocess.TimeoutExpired):
        bounded_run([sys.executable,'-c','import time; time.sleep(10)'],timeout=.2)


@pytest.mark.skipif(os.name!='nt',reason='Windows construction backend')
def test_bounded_process_stops_excessive_output():
    from lab.process_guard import bounded_run
    with pytest.raises(ValueError,match='output'):
        bounded_run([sys.executable,'-c','print("x"*100000)'],timeout=3,output_limit=10000)
