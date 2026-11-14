"""Disposable Linux tasks. No generated code executes in the controller process."""
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from .docker_policy import LABEL,USER,create_options,validate_inspect,pack_files,unpack_artifacts

WORKER_IMAGE='strategy-agent-lab-worker:0.1.0'
VOLUME_OPTIONS={'type':'tmpfs','device':'tmpfs','o':'nosuid,nodev,size=16777216,nr_inodes=512,uid=10001,gid=10001,mode=700'}
CLEANUP_GRACE=1.0


class _ExecStream:
    """Own the attach transport even if cancellation precedes exec_start's return."""
    def __init__(self):
        self.lock=threading.Lock();self.cancelled=threading.Event()
        self.stream=None;self.closing=False;self.close_done=threading.Event();self.close_error=None

    def attach(self,stream):
        with self.lock:self.stream=stream
        if self.cancelled.is_set():self.close_stream()

    def cancel(self):
        self.cancelled.set();self.close_stream()

    def close_stream(self):
        with self.lock:
            if self.stream is None or self.closing:return
            self.closing=True
        def close():
            try:self.stream.close()
            except Exception:self.close_error='Docker exec stream cleanup failed.'
            finally:self.close_done.set()
        threading.Thread(target=close,daemon=True).start()


def validate_volume(attrs,name,owner,task):
    if attrs.get('Name')!=name or attrs.get('Driver')!='local' or attrs.get('Options')!=VOLUME_OPTIONS or attrs.get('Labels',{}).get(LABEL)!=owner or attrs.get('Labels',{}).get('lab.task')!=task:
        raise ValueError('Docker task volume policy verification failed.')


def backend():
    choice=os.getenv('LAB_EXECUTION_BACKEND','mxc')
    if choice not in {'mxc','docker'}:raise ValueError('LAB_EXECUTION_BACKEND must be mxc or docker; no host fallback.')
    return choice


def installation_id(root):
    path=Path(root)/'installation-id';path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open('x') as f:f.write(uuid.uuid4().hex)
    except FileExistsError:pass
    value=path.read_text().strip()
    if len(value)!=32 or any(c not in '0123456789abcdef' for c in value):raise ValueError('Invalid installation identity.')
    return value


def connect():
    import docker
    client=None
    try:
        client=docker.from_env(timeout=10);info=client.info()
        if info.get('OSType')!='linux' or not any('seccomp' in x and 'unconfined' not in x for x in info.get('SecurityOptions',[])):
            raise ValueError('Docker requires Linux containers and default seccomp.')
        if int(client.version()['Version'].split('.')[0])<25:raise ValueError('Docker Engine 25 or newer is required.')
        return client
    except Exception as exc:
        if client is not None:client.close()
        if isinstance(exc,ValueError):raise
        raise ValueError('Docker unavailable. Start Docker Desktop in Linux-container mode, then run the launch script. No native fallback.') from None


def cleanup_owned(root):
    client=connect();owner=installation_id(root)
    try:
        for container in client.containers.list(all=True,filters={'label':LABEL+'='+owner}):
            if container.labels.get(LABEL)==owner and container.labels.get('lab.task'):container.remove(force=True,v=True)
        for volume in client.volumes.list(filters={'label':LABEL+'='+owner}):
            labels=volume.attrs.get('Labels',{})
            if labels.get(LABEL)==owner and labels.get('lab.task'):volume.remove()
    finally:client.close()


class DockerTask:
    def __init__(self,installation,task=None,*,client=None,volume=None,readonly=False,wall_seconds=480):
        self.close_lock=threading.Lock()
        self.cleanup_done=threading.Event();self.cleanup_started=False;self.cleanup_error=None;self.execution=None
        self.owns_client=client is None;self.client_closed=False
        self.client=client or connect();self.installation=installation;self.task=task or uuid.uuid4().hex
        self.volume,self.readonly=volume,readonly;self.wall_seconds=wall_seconds;self.container=None;self.timer=None;self.closed=False
        self.owned_volume=None

    def __enter__(self):
        try:image=self.client.images.get(WORKER_IMAGE)
        except Exception:
            self.close()
            raise ValueError('Worker image unavailable. Run the maintained launch script to build it; no automatic task pull.') from None
        self.image=image.id;self.image_env=image.attrs.get('Config',{}).get('Env',[])
        allowed={'PATH','LANG','GPG_KEY','PYTHON_VERSION','PYTHON_SHA256','HOME','PYTHONDONTWRITEBYTECODE'}
        if any(e.split('=',1)[0] not in allowed for e in self.image_env):
            self.close();raise ValueError('Worker image has unexpected environment; rebuild with the launch script.')
        try:
            if self.volume is None:
                self.volume='lab-task-'+self.installation+'-'+self.task+'-'+uuid.uuid4().hex
                self.owned_volume=self.client.volumes.create(name=self.volume,driver='local',driver_opts=dict(VOLUME_OPTIONS),labels={LABEL:self.installation,'lab.task':self.task})
                self.owned_volume.reload()
                validate_volume(self.owned_volume.attrs,self.volume,self.installation,self.task)
            self.container=self.client.containers.create(**create_options(self.image,self.installation,self.task,volume=self.volume,readonly=self.readonly))
            self.inspect();self.container.start();self.inspect()
            self.deadline=time.monotonic()+self.wall_seconds
            self.timer=threading.Timer(self.wall_seconds,self._expire);self.timer.daemon=True;self.timer.start()
            return self
        except BaseException:
            self.__exit__(*sys.exc_info());raise

    def inspect(self):
        if self.closed:raise ValueError('Docker task already closed; no further work permitted.')
        self.container.reload()
        validate_inspect(self.container.attrs,self.image,self.installation,self.task,volume=self.volume,readonly=self.readonly,image_env=self.image_env)

    def close(self):
        with self.close_lock:
            self.closed=True
            if self.timer:self.timer.cancel()
            if self.execution:self.execution.cancel()
            if not self.cleanup_started:
                self.cleanup_started=True;self.cleanup_deadline=time.monotonic()+CLEANUP_GRACE
                threading.Thread(target=self._remove_owned,daemon=True).start()
        if not self.cleanup_done.wait(max(0,self.cleanup_deadline-time.monotonic())):
            raise ValueError('Owned Docker task cleanup pending after bounded wait. Restart the app to retry owned-task cleanup.')
        if self.cleanup_error:raise ValueError(self.cleanup_error)

    def _remove_owned(self):
        try:
            if self.container:self.container.remove(force=True,v=True)
            if self.owned_volume is not None:
                self.owned_volume.reload()
                attrs=self.owned_volume.attrs;labels=attrs.get('Labels',{})
                if attrs.get('Name')!=self.volume or labels.get(LABEL)!=self.installation or labels.get('lab.task')!=self.task:
                    raise ValueError('Owned volume identity could not be verified; refusing deletion.')
                self.owned_volume.remove()
        except Exception:
            self.cleanup_error='Owned Docker task cleanup failed. Restart the app to retry owned-task cleanup.'
        finally:
            try:
                if self.owns_client and not self.client_closed:
                    self.client.close();self.client_closed=True
            except Exception:self.cleanup_error='Owned Docker client cleanup failed. Restart the app to retry owned-task cleanup.'
            finally:self.cleanup_done.set()

    def _expire(self):
        try:self.close()
        except ValueError:pass  # Retained cleanup state is reported by the waiting task/context.

    def __exit__(self,kind,error,traceback):
        try:self.close()
        except ValueError as exc:
            if error is None:raise
            error.add_note(str(exc))

    def seed(self,files):
        if self.readonly:raise ValueError('Read-only task cannot receive writes.')
        if not self.container.put_archive('/workspace',pack_files(files)):raise ValueError('Task input copy failed.')

    def run(self,args,*,timeout=20,output_limit=65536):
        if self.closed or time.monotonic()>=self.deadline:raise ValueError('Docker task wall-time limit reached.')
        args=['python' if a==sys.executable else a for a in args]
        deadline=min(self.deadline,time.monotonic()+timeout)
        operation=_ExecStream();done=threading.Event();result=[];errors=[]
        with self.close_lock:
            if self.closed:raise ValueError('Docker task already closed; no further work permitted.')
            if self.execution is not None:raise ValueError('Concurrent Docker commands are not permitted.')
            self.execution=operation
        def execute():
            try:
                self.inspect()
                handle=self.client.api.exec_create(self.container.id,args,user=USER,workdir='/workspace',environment={'PYTHONDONTWRITEBYTECODE':'1'},stdout=True,stderr=True)
                if operation.cancelled.is_set():return
                stream=self.client.api.exec_start(handle['Id'],stream=True,demux=True)
                operation.attach(stream);output=[bytearray(),bytearray()]
                for pair in stream:
                    if operation.cancelled.is_set():return
                    for index,chunk in enumerate(pair):
                        if not chunk:continue
                        if sum(map(len,output))+len(chunk)>output_limit:raise ValueError('Docker process output exceeds limit.')
                        output[index].extend(chunk)
                if operation.cancelled.is_set():return
                status=self.client.api.exec_inspect(handle['Id'])
                if status.get('Running') or status.get('ExitCode') is None:raise ValueError('Docker process did not finish.')
                result.append(subprocess.CompletedProcess(args,status['ExitCode'],*[x.decode('utf-8','replace') for x in output]))
            except Exception as exc:errors.append(exc)
            finally:operation.close_stream();done.set()
        # A broken daemon/transport cannot occupy asyncio's non-daemon executor forever.
        threading.Thread(target=execute,daemon=True).start()
        try:
            while not done.wait(max(0,min(.02,deadline-time.monotonic()))):
                if time.monotonic()>=deadline:raise ValueError('Docker process exceeded time limit.')
                if operation.cancelled.is_set():raise ValueError('Docker task cancelled or wall-time limit reached.')
            if operation.cancelled.is_set():raise ValueError('Docker task cancelled or wall-time limit reached.')
            if errors:raise errors[0]
            if not operation.close_done.wait(.1) or operation.close_error:raise ValueError('Docker exec stream cleanup failed or remains pending.')
            return result[0]
        except BaseException as exc:
            operation.cancel();diagnostics=[]
            try:self.close()
            except ValueError as cleanup:diagnostics.append(str(cleanup))
            if operation.stream is not None and (not operation.close_done.wait(.1) or operation.close_error):
                diagnostics.append(operation.close_error or 'Docker exec stream cleanup pending.')
            if not done.is_set():diagnostics.append('Docker exec reader cleanup pending; trusted waiting stopped.')
            if isinstance(exc,Exception):
                primary=str(exc) if isinstance(exc,ValueError) else 'Docker command failed; no fallback.'
                raise ValueError(' '.join([primary,*diagnostics])) from None
            for diagnostic in diagnostics:exc.add_note(diagnostic)
            raise
        finally:
            operation.close_stream()
            with self.close_lock:
                if self.execution is operation:self.execution=None

    def collect(self):
        self.inspect();self.container.pause()
        try:return unpack_artifacts(self.container.get_archive('/workspace')[0])
        finally:self.container.unpause()

    def probe(self):
        script="import os,pathlib,socket;assert os.getuid()==10001;assert not any('KEY' in k or 'TOKEN' in k for k in os.environ if k!='GPG_KEY');assert not pathlib.Path('/var/run/docker.sock').exists();assert not pathlib.Path('/data').exists();blocked=0\n"
        script+="assert pathlib.Path('/outside-canary').exists()\ntry:pathlib.Path('/outside-canary').read_text()\nexcept OSError:blocked+=1\n"
        script+="try:pathlib.Path('/outside-canary').write_text('bad')\nexcept OSError:blocked+=1\n"
        script+="try:socket.create_connection(('1.1.1.1',443),.3)\nexcept OSError:blocked+=1\n"
        script+="assert set(os.listdir('/sys/class/net'))=={'lo'}\n"
        if self.readonly:
            script+="try:pathlib.Path('/workspace/probe-created').write_text('bad')\nexcept OSError:blocked+=1\n"
        script+=f"assert blocked=={4 if self.readonly else 3};print('DOCKER_ISOLATION_OK')"
        result=self.run(['python','-I','-B','-c',script])
        if result.returncode or result.stdout.strip()!='DOCKER_ISOLATION_OK':raise ValueError('Docker isolation probe failed; no model request sent.')


class DockerBoundary:
    """Per-call read-only volume, seeded without binding controller filesystem paths."""
    def __init__(self,work,home):self.work=Path(work);self.home=Path(home)

    def probe(self):
        # run() creates and probes the actual read-only scope before each command.
        pass

    def run(self,args,*,output_limit=65536):
        from .project_evaluator import bounded_inventory
        files={p.relative_to(self.work).as_posix():(p.read_bytes() if p.suffix=='.bin' else p.read_text(encoding='utf-8')) for p,is_dir,_ in bounded_inventory(self.work) if not is_dir}
        client=connect()
        data=Path(os.environ['LAB_DATA_ROOT'])/'runs' if os.environ.get('LAB_DATA_ROOT') else next((p for p in self.home.parents if p.name=='runs'),self.home.parent)
        owner=installation_id(data)
        tid=uuid.uuid4().hex;name='lab-task-'+owner+'-'+tid
        volume=client.volumes.create(name=name,driver='local',driver_opts=dict(VOLUME_OPTIONS),labels={LABEL:owner,'lab.task':tid})
        try:
            volume.reload();validate_volume(volume.attrs,name,owner,tid)
            # Keep seed alive: tmpfs contents disappear when the last mount is released.
            with DockerTask(owner,tid,client=client,volume=name,wall_seconds=60) as seed:
                seed.seed(files)
                with DockerTask(owner,tid,client=client,volume=name,readonly=True,wall_seconds=30) as task:
                    task.probe();return task.run(args,output_limit=output_limit)
        finally:
            try:volume.remove()
            finally:client.close()


def boundary_factory(work,home):
    if backend()=='docker':return DockerBoundary(work,home)
    from .project_evaluator import MXCBoundary
    return MXCBoundary(work,home)
