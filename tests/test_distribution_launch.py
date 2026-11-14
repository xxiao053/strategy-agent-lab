import os
import shutil
import subprocess
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
GIT_SH=Path(shutil.which('git') or '.').resolve().parent.parent/'bin/sh.exe'
SH=shutil.which('sh') or (str(GIT_SH) if GIT_SH.exists() else None)
WINDOWS_PS=Path(os.environ.get('SystemRoot', 'C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'


@pytest.mark.skipif(os.name!='nt' or not WINDOWS_PS.exists(),reason='Windows PowerShell 5.1 required')
@pytest.mark.parametrize('action,engine_exit,expected',[
    ('start',0,['info --format {{.OSType}}','compose build worker controller','compose up -d --wait --wait-timeout 90 controller']),
    ('stop',0,['info --format {{.OSType}}','compose stop']),
    ('restart',0,['info --format {{.OSType}}','compose restart controller']),
    ('start',1,['info --format {{.OSType}}']),
    ('invalid',0,[]),
])
def test_windows_entry_runs_under_restricted_policy_without_changing_it(tmp_path,action,engine_exit,expected):
    # Removing the wrapper's process-only policy or path quoting must fail here.
    entry=ROOT/'scripts/start-docker.cmd'
    assert entry.is_file(), 'Windows needs an entry point that works with its default script policy'
    scripts=tmp_path/'download with spaces'/'scripts';scripts.mkdir(parents=True)
    for name in ('start-docker.ps1','start-docker.cmd'):
        shutil.copyfile(ROOT/'scripts'/name,scripts/name)
    fake=tmp_path/'docker.cmd'
    fake.write_text('@echo off\necho CALLED %*\nexit /b '+str(engine_exit)+'\n',encoding='ascii')
    env=dict(os.environ,PATH=str(tmp_path)+os.pathsep+os.environ['PATH'])
    # A pytest process launched by pwsh must not inject its PS7 modules into PS5.1.
    env={key:value for key,value in env.items() if key.casefold()!='psmodulepath'}
    quoted=str(scripts/'start-docker.cmd').replace("'","''")
    command=f"& '{quoted}' {action}; $launchResult=$LASTEXITCODE; Write-Output ('POLICY='+ (Get-ExecutionPolicy)); exit $launchResult"
    result=subprocess.run([str(WINDOWS_PS),'-NoProfile','-ExecutionPolicy','Restricted','-Command',command],
                          cwd=tmp_path,env=env,capture_output=True,text=True,timeout=20)
    calls=[line.removeprefix('CALLED ') for line in result.stdout.splitlines() if line.startswith('CALLED ')]
    assert calls==expected, result.stdout+result.stderr
    assert 'POLICY=Restricted' in result.stdout
    assert (result.returncode==0)==(engine_exit==0 and action!='invalid'),result.stdout+result.stderr


@pytest.mark.skipif(not SH,reason='POSIX shell not available')
@pytest.mark.parametrize('action,last',[('start','compose up -d --wait --wait-timeout 90 controller'),('stop','compose stop'),('restart','compose restart controller')])
def test_posix_launch_executes_safe_commands(tmp_path,action,last):
    mock=tmp_path/'docker';mock.write_text('#!/bin/sh\nprintf "CALLED %s\\n" "$*"\n',encoding='utf-8');mock.chmod(0o755)
    env=dict(os.environ,LAB_LAUNCH=(ROOT/'scripts/start-docker.sh').as_posix(),LAB_ACTION=action)
    result=subprocess.run([SH,'-c','PATH="$PWD:$PATH"; export PATH; sh "$LAB_LAUNCH" "$LAB_ACTION"'],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    calls=[line.removeprefix('CALLED ') for line in result.stdout.splitlines() if line.startswith('CALLED ')]
    assert calls[0]=='info --format {{.OSType}}' and calls[-1]==last
    assert not any('-v' in call or 'down' in call or 'prune' in call for call in calls)


@pytest.mark.skipif(not shutil.which('pwsh'),reason='PowerShell not installed')
@pytest.mark.parametrize('action,expected',[
 ('start',['info --format {{.OSType}}','compose build worker controller','compose up -d --wait --wait-timeout 90 controller']),
 ('stop',['info --format {{.OSType}}','compose stop']),('restart',['info --format {{.OSType}}','compose restart controller'])])
def test_powershell_launch_preserves_data_and_limits_services(action,expected):
    command="function docker { Write-Output ('CALLED '+($args -join ' ')); $global:LASTEXITCODE=0 }; & '"+str(ROOT/'scripts/start-docker.ps1')+"' "+action
    result=subprocess.run(['pwsh','-NoProfile','-Command',command],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    calls=[line.removeprefix('CALLED ') for line in result.stdout.splitlines() if line.startswith('CALLED ')]
    assert calls==expected


@pytest.mark.skipif(not shutil.which('pwsh'),reason='PowerShell not installed')
def test_launcher_does_not_build_when_engine_unavailable():
    command="function docker { Write-Output ('CALLED '+($args -join ' ')); $global:LASTEXITCODE=1 }; & '"+str(ROOT/'scripts/start-docker.ps1')+"'"
    result=subprocess.run(['pwsh','-NoProfile','-Command',command],capture_output=True,text=True,timeout=15)
    assert result.returncode!=0 and 'compose build' not in result.stdout


def test_runtime_status_does_not_claim_engine_verification(tmp_path,monkeypatch):
    from lab.api import create_app
    from fastapi.testclient import TestClient
    monkeypatch.setenv('LAB_EXECUTION_BACKEND','docker')
    def unavailable():raise ValueError('Docker unavailable. Start Docker.')
    monkeypatch.setattr('lab.docker_runtime.connect',unavailable)
    with TestClient(create_app(root=tmp_path),base_url='http://localhost') as client:
        r=client.get('/api/workspace/runtime-status')
    assert r.status_code==200 and r.json()['available'] is False and r.json()['backend']=='docker'


def test_controller_cleans_owned_tasks_before_and_after_serving(tmp_path,monkeypatch):
    import lab.container_app as entry
    import uvicorn
    calls=[];monkeypatch.setenv('LAB_DATA_ROOT',str(tmp_path))
    monkeypatch.setattr(entry,'cleanup_owned',lambda root:calls.append(('cleanup',root)))
    monkeypatch.setattr(uvicorn,'run',lambda *a,**kw:calls.append(('serve',kw['host'])))
    entry.main()
    assert calls==[('cleanup',tmp_path/'runs'),('serve','0.0.0.0'),('cleanup',tmp_path/'runs')]
