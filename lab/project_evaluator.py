"""Replaceable isolated evaluator; no host import/eval/exec of generated source."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import time
from .build_runtime import runtime_config, runtime_environment
from .process_guard import bounded_run
from .execution_contract import artifact_map, canonical, parse_output
from .project_limits import DECISION_INPUT_BYTES


class MXCBoundary:
    def __init__(self,work,home):
        self.work,self.home=Path(work),Path(home)
        self.codex=shutil.which('codex')
        if os.name!='nt' or not self.codex:
            raise ValueError('Historical execution requires an available Windows MXC isolation runtime. No host fallback.')
        (self.home/'config.toml').write_text(runtime_config('http://127.0.0.1:1','offline','',workspace_access='read'),encoding='utf-8')

    def run(self,args,*,output_limit=65536):
        return bounded_run([self.codex,'sandbox','--permission-profile','builder','--cd',str(self.work),'--']+args,
                           cwd=self.work,env=runtime_environment(self.home),timeout=20,output_limit=output_limit)

    def probe(self):
        canary=self.home/'outside-canary.txt';canary.write_text('boundary-only',encoding='utf-8')
        inside=self.work/'readonly-probe.txt';inside.write_text('readable-input',encoding='utf-8')
        script='import pathlib,socket; p=pathlib.Path('+repr(str(canary))+'); blocked=0\n'
        script+="try: p.read_text()\nexcept OSError: blocked+=1\ntry: p.write_text('bad')\nexcept OSError: blocked+=1\n"
        script+="inside=pathlib.Path('readonly-probe.txt'); assert inside.read_text()=='readable-input'\n"
        script+="try: inside.write_text('bad')\nexcept OSError: blocked+=1\ntry: pathlib.Path('probe-created.txt').write_text('bad')\nexcept OSError: blocked+=1\n"
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));listener.listen()
            script+=f"try: socket.create_connection(('127.0.0.1',{listener.getsockname()[1]}),1)\nexcept OSError: blocked+=1\n"
            script+="print('PROJECT_ISOLATION_OK' if blocked==5 else 'FAILED');raise SystemExit(0 if blocked==5 else 2)"
            result=self.run([sys.executable,'-I','-c',script])
        inside.unlink()
        if result.returncode or result.stdout.strip()!='PROJECT_ISOLATION_OK':
            raise ValueError('Historical isolation probe failed. No strategy or model request executed.')


def bounded_inventory(root):
    """Defense in depth after read-only execution, never an output quota substitute."""
    root=Path(root);deadline=time.monotonic()+2;entries=[];total=0;context_total=0;pending=[(root,0)]
    if root.is_symlink() or getattr(root.lstat(),'st_file_attributes',0)&0x400:
        raise ValueError('Unsupported scope link; bounded inspection stopped.')
    while pending:
        directory,depth=pending.pop()
        if depth>8:raise ValueError('Filesystem depth limit exceeded.')
        with os.scandir(directory) as children:
            for child in children:
                if time.monotonic()>deadline or len(entries)>=512:raise ValueError('Filesystem inspection limit exceeded.')
                stat=child.stat(follow_symlinks=False)
                if child.is_symlink() or getattr(stat,'st_file_attributes',0)&0x400:
                    raise ValueError('Unsupported filesystem link; bounded inspection stopped.')
                path=Path(child.path);is_dir=child.is_dir(follow_symlinks=False)
                if not is_dir:
                    if not child.is_file(follow_symlinks=False):raise ValueError('Unsupported filesystem entry.')
                    is_context=path.relative_to(root).as_posix() in {'context.json','project/context.json'}
                    if is_context:context_total+=stat.st_size
                    else:total+=stat.st_size
                    if stat.st_size>(DECISION_INPUT_BYTES if is_context else 1500000) or total>2500000 or context_total>DECISION_INPUT_BYTES:
                        raise ValueError('Filesystem byte limit exceeded.')
                entries.append((path,is_dir,stat.st_size))
                if is_dir:pending.append((path,depth+1))
    return entries


def source_hash(work):
    entries=bounded_inventory(work);result={};deadline=time.monotonic()+2
    for path,is_dir,size in entries:
        if time.monotonic()>deadline:raise ValueError('Source verification time limit exceeded.')
        if not is_dir:
            with path.open('rb') as source:content=source.read(size+1)
            if len(content)!=size:raise ValueError('Source changed during verification.')
            result[path.relative_to(work).as_posix()]=hashlib.sha256(content).hexdigest()
    return result


def bounded_cleanup(root):
    """Only remove a verified bounded scope; retain anomalous trees for operator review."""
    try:entries=bounded_inventory(root)
    except (ValueError,OSError):raise ValueError('Isolated scope retained: bounded cleanup inspection failed.') from None
    deadline=time.monotonic()+2
    for path,is_dir,_ in sorted(entries,key=lambda item:len(item[0].parts),reverse=True):
        if time.monotonic()>deadline:raise ValueError('Isolated scope retained: bounded cleanup time limit.')
        if is_dir:path.rmdir()
        else:path.unlink()
    Path(root).rmdir()


class IsolatedEvaluator:
    def __init__(self,folder,artifacts,*,boundary_factory=None):
        from .docker_runtime import boundary_factory as selected_boundary
        self.folder=Path(folder);self.files=artifact_map(artifacts);self.boundary_factory=boundary_factory or selected_boundary

    def decide(self,context):
        payload=canonical(context)
        if len(payload.encode())>DECISION_INPUT_BYTES:raise ValueError('Decision input size exceeds 8 MiB limit.')
        self.folder.mkdir(parents=True,exist_ok=True)
        # A fresh, disposable scope for each cutoff. Never copy the full snapshot or prior scope.
        scope=tempfile.mkdtemp(prefix='decision-',dir=self.folder)
        try:
            root=Path(scope);work=root/'project';home=root/'runtime';work.mkdir();home.mkdir()
            for name,text in self.files.items():
                if not name.endswith('.py') or name.split('/')[-1].startswith('test_'):continue
                path=work/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
            (work/'context.json').write_text(payload,encoding='utf-8')
            before=source_hash(work)
            boundary=self.boundary_factory(work,home);boundary.probe()
            script=("import sys,json,runpy,os;sys.dont_write_bytecode=True;sys.path.insert(0,os.getcwd());"
                    "context=json.load(open('context.json',encoding='utf-8'));"
                    "strategy=runpy.run_path('strategy.py');result=strategy['decide'](context);"
                    "print(json.dumps(result,allow_nan=False,separators=(',',':')))")
            result=boundary.run([sys.executable,'-I','-B','-c',script])
            if source_hash(work)!=before:raise ValueError('Strategy changed immutable input/source files.')
            if result.returncode:raise ValueError('Isolated strategy failed; no decision accepted.')
            return parse_output(result.stdout.strip())
        finally:bounded_cleanup(scope)
