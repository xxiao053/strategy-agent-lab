import pytest
from types import SimpleNamespace
from tests.test_docker_policy import inspected


class Container:
    id='owned'
    def __init__(self,attrs):self.attrs=attrs;self.removed=False;self.started=False;self.events=[]
    def reload(self):pass
    def start(self):self.started=True
    def remove(self,**kwargs):self.removed=True;self.events.append('container-removed')
    def put_archive(self,path,archive):
        assert path=='/workspace' and self.attrs['HostConfig']['ReadonlyRootfs']
        if not self.attrs['Mounts']:raise ValueError('container rootfs is marked read-only')
        return True


def client(attrs):
    c=Container(attrs);calls=[];volumes=[]
    def create(**kwargs):
        calls.append(kwargs)
        if kwargs.get('mounts'):
            mount=kwargs['mounts'][0]
            c.attrs['HostConfig']['Tmpfs'].pop('/workspace',None)
            c.attrs['HostConfig']['Mounts']=kwargs['mounts']
            c.attrs['Mounts']=[{'Type':mount['Type'],'Name':mount['Source'],'Destination':mount['Target'],'RW':not mount['ReadOnly']}]
        return c
    def create_volume(**kwargs):
        volume=SimpleNamespace(attrs={'Name':kwargs['name'],'Driver':kwargs['driver'],'Options':kwargs['driver_opts'],'Labels':kwargs['labels']},reload=lambda:None,remove=lambda:c.events.append('volume-removed'))
        volumes.append(volume);return volume
    image=SimpleNamespace(id='sha256:reviewed',attrs={'Config':{'Env':[]}})
    return SimpleNamespace(containers=SimpleNamespace(create=create),images=SimpleNamespace(get=lambda name:image),volumes=SimpleNamespace(create=create_volume,created=volumes)),c,calls


def test_task_removes_owned_container_on_inspection_failure():
    from lab.docker_runtime import DockerTask
    attrs=inspected();attrs['HostConfig']['NetworkMode']='bridge';docker,c,calls=client(attrs)
    with pytest.raises(ValueError,match='policy'):
        with DockerTask('install','task',client=docker):pass
    assert c.removed and not c.started


def test_task_always_cleans_up_and_never_mounts_controller():
    from lab.docker_runtime import DockerTask
    docker,c,calls=client(inspected())
    with pytest.raises(RuntimeError):
        with DockerTask('install','task',client=docker):raise RuntimeError('fixture')
    assert c.removed and c.started
    assert calls[0]['mounts'][0]['Type']=='volume' and not calls[0].get('volumes')
    assert c.events==['container-removed','volume-removed']


def test_default_seed_uses_owned_bounded_volume_under_readonly_root():
    from lab.docker_runtime import DockerTask
    docker,c,calls=client(inspected())
    with DockerTask('install','task',client=docker) as task:
        task.seed({'reference.txt':'full Unicode: 中文 β'})
        volume=docker.volumes.created[0]
        assert volume.attrs['Options']=={'type':'tmpfs','device':'tmpfs','o':'nosuid,nodev,size=16777216,nr_inodes=512,uid=10001,gid=10001,mode=700'}
        assert volume.attrs['Driver']=='local'
        assert volume.attrs['Labels']=={'lab.installation':'install','lab.task':'task'}
        assert calls[0]['mounts']==[{'Type':'volume','Source':volume.attrs['Name'],'Target':'/workspace','ReadOnly':False}]
        assert calls[0]['read_only'] is True and '/workspace' not in calls[0]['tmpfs']
    assert c.events==['container-removed','volume-removed']


@pytest.mark.parametrize('phase',['container-create','volume-inspect','container-inspect','start','seed','timeout'])
def test_owned_volume_cleanup_after_lifecycle_failures(phase):
    from lab.docker_runtime import DockerTask
    docker,c,_=client(inspected())
    def fail(*a,**kw):raise ValueError('fixture failure')
    if phase=='container-create':docker.containers.create=fail
    if phase=='volume-inspect':
        original=docker.volumes.create
        def tampered(**kw):
            volume=original(**kw);volume.attrs['Options']={};return volume
        docker.volumes.create=tampered
    if phase=='container-inspect':c.attrs['Config']['User']='root'
    if phase=='start':c.start=fail
    if phase=='seed':c.put_archive=fail
    with pytest.raises(ValueError):
        with DockerTask('install','task',client=docker) as task:
            if phase=='timeout':task._expire();task.inspect()
            else:task.seed({'input.txt':'cutoff'})
    assert len(docker.volumes.created)==1
    assert c.events==(['volume-removed'] if phase in {'container-create','volume-inspect'} else ['container-removed','volume-removed'])


def test_external_shared_volume_is_never_removed_by_task():
    from lab.docker_runtime import DockerTask
    docker,c,calls=client(inspected())
    with DockerTask('install','task',client=docker,volume='shared-seed',readonly=True):pass
    assert docker.volumes.created==[] and c.events==['container-removed']
    assert calls[0]['mounts'][0]['ReadOnly'] is True


def test_forged_owned_volume_labels_never_authorize_deletion():
    from lab.docker_runtime import DockerTask
    docker,c,calls=client(inspected());original=docker.volumes.create
    def foreign(**kw):
        volume=original(**kw);volume.attrs['Labels']={'lab.installation':'other','lab.task':'task'};return volume
    docker.volumes.create=foreign
    with pytest.raises(ValueError):
        with DockerTask('install','task',client=docker):pass
    assert not calls and c.events==[]


def test_failed_container_removal_retains_owned_volume_for_startup_cleanup():
    from lab.docker_runtime import DockerTask
    docker,c,_=client(inspected())
    def fail(**kw):raise RuntimeError('daemon unavailable')
    c.remove=fail
    with pytest.raises(ValueError,match='cleanup'):
        with DockerTask('install','task',client=docker):pass
    assert len(docker.volumes.created)==1 and c.events==[]


def test_volume_creation_failure_closes_owned_client_without_container(monkeypatch):
    import lab.docker_runtime as runtime
    docker,c,calls=client(inspected());closed=[];docker.close=lambda:closed.append(True)
    def fail(**kw):raise ValueError('volume create failed')
    docker.volumes.create=fail
    monkeypatch.setattr(runtime,'connect',lambda:docker)
    with pytest.raises(ValueError,match='volume create'):
        with runtime.DockerTask('install','task'):pass
    assert not calls and not c.events and closed==[True]


def test_missing_image_fails_without_implicit_pull():
    from lab.docker_runtime import DockerTask
    docker,c,calls=client(inspected())
    def absent(name):raise RuntimeError('missing')
    docker.images.get=absent
    with pytest.raises(ValueError,match='launch'):
        with DockerTask('install','task',client=docker):pass
    assert not calls


def test_volume_tampering_rejected_before_seed():
    from lab.docker_runtime import validate_volume
    expected={'Name':'owned','Driver':'local','Labels':{'lab.installation':'install','lab.task':'task'},'Options':{'type':'tmpfs','device':'tmpfs','o':'nosuid,nodev,size=16777216,nr_inodes=512,uid=10001,gid=10001,mode=700'}}
    validate_volume(expected,'owned','install','task')
    expected['Options']['device']='/host'
    with pytest.raises(ValueError):validate_volume(expected,'owned','install','task')


def test_readonly_boundary_removes_both_tasks_and_volume_on_failure(tmp_path,monkeypatch):
    import lab.docker_runtime as runtime
    events=[];work=tmp_path/'work';home=tmp_path/'home';work.mkdir();home.mkdir();(work/'strategy.py').write_text('pass')
    class Volume:
        def reload(self):pass
        def remove(self):events.append('volume-removed')
    def create(**kwargs):
        v=Volume();v.attrs={'Name':kwargs['name'],'Driver':kwargs['driver'],'Options':kwargs['driver_opts'],'Labels':kwargs['labels']};return v
    class Task:
        def __init__(self,*args,**kwargs):self.readonly=kwargs.get('readonly',False)
        def __enter__(self):events.append('reader' if self.readonly else 'seed');return self
        def __exit__(self,*args):events.append('reader-removed' if self.readonly else 'seed-removed')
        def seed(self,files):assert files=={'strategy.py':'pass'}
        def probe(self):raise ValueError('fixture isolation failure')
    monkeypatch.setattr(runtime,'connect',lambda:SimpleNamespace(volumes=SimpleNamespace(create=create),close=lambda:None))
    monkeypatch.setattr(runtime,'DockerTask',Task)
    with pytest.raises(ValueError,match='fixture'):runtime.DockerBoundary(work,home).run(['python'])
    assert events==['seed','reader','reader-removed','seed-removed','volume-removed']


def test_startup_cleanup_never_removes_other_installations(monkeypatch,tmp_path):
    import lab.docker_runtime as runtime
    owner=runtime.installation_id(tmp_path);removed=[]
    def item(label,task,name):return SimpleNamespace(labels={'lab.installation':label,'lab.task':task},remove=lambda **kw:removed.append(name))
    containers=[item(owner,'task','owned'),item('other','task','foreign'),item(owner,None,'not-task')]
    volume=SimpleNamespace(attrs={'Labels':{'lab.installation':owner}},remove=lambda:removed.append('not-task-volume'))
    client=SimpleNamespace(containers=SimpleNamespace(list=lambda **kw:containers),volumes=SimpleNamespace(list=lambda **kw:[volume]),close=lambda:None)
    monkeypatch.setattr(runtime,'connect',lambda:client)
    runtime.cleanup_owned(tmp_path)
    assert removed==['owned']


def test_owned_client_is_closed_but_shared_seed_client_is_not(monkeypatch):
    import lab.docker_runtime as runtime
    docker,c,_=client(inspected());closed=[];docker.close=lambda:closed.append(True)
    monkeypatch.setattr(runtime,'connect',lambda:docker)
    with runtime.DockerTask('install','task'):pass
    assert closed==[True]
    closed.clear()
    with runtime.DockerTask('install','task',client=docker):pass
    assert closed==[]


def test_concurrent_close_waits_for_container_removal(monkeypatch):
    import threading
    import lab.docker_runtime as runtime
    docker,c,_=client(inspected());removing=threading.Event();release=threading.Event();closed=threading.Event();events=[]
    def remove(**kwargs):
        removing.set();assert release.wait(2);events.append('removed')
    def close():events.append('closed');closed.set()
    c.remove=remove;docker.close=close
    monkeypatch.setattr(runtime,'connect',lambda:docker)
    task=runtime.DockerTask('install','task').__enter__()
    first=threading.Thread(target=task.close);second=threading.Thread(target=task.close)
    try:
        first.start();assert removing.wait(2);second.start()
        assert not closed.wait(.1), 'Client closed while container removal was in flight'
    finally:
        release.set();first.join(2);second.join(2)
    assert events==['removed','closed']


def test_failed_engine_preflight_closes_client(monkeypatch):
    import docker
    from lab.docker_runtime import connect
    closed=[]
    fake=SimpleNamespace(info=lambda:{'OSType':'windows'},close=lambda:closed.append(True))
    monkeypatch.setattr(docker,'from_env',lambda **kw:fake)
    with pytest.raises(ValueError,match='Linux'):connect()
    assert closed==[True]


@pytest.mark.parametrize('failure',['remove-fails','remove-hangs','stream-close-ineffective','stream-close-hangs'])
def test_silent_exec_timeout_cancels_stream_and_bounds_cleanup(failure):
    import threading
    import time
    from lab.docker_runtime import DockerTask
    docker,c,_=client(inspected());reading=threading.Event();release=threading.Event();remove_release=threading.Event();stream_closed=threading.Event();done=threading.Event();errors=[]
    class Stream:
        def __iter__(self):return self
        def __next__(self):reading.set();release.wait(3);raise StopIteration
        def close(self):
            stream_closed.set()
            if failure=='stream-close-hangs':release.wait(3)
            if failure!='stream-close-ineffective':release.set()
    def remove(**kwargs):
        if failure=='remove-hangs':remove_release.wait(3)
        raise RuntimeError('daemon unavailable')
    c.remove=remove
    docker.api=SimpleNamespace(exec_create=lambda *a,**kw:{'Id':'exec'},exec_start=lambda *a,**kw:Stream(),exec_inspect=lambda *a:{'Running':False,'ExitCode':0})
    task=DockerTask('install','task',client=docker)
    def execute():
        try:
            with task:task.run(['python','silent'],timeout=.05)
        except Exception as exc:errors.append(str(exc))
        finally:done.set()
    thread=threading.Thread(target=execute,daemon=True);started=time.monotonic()
    try:
        thread.start();assert reading.wait(1)
        assert done.wait(1.5), 'Trusted caller remained blocked past timeout and bounded cleanup grace'
        assert stream_closed.is_set(), 'Stream must close independently of failed removal'
        assert len(errors)==1 and 'time limit' in errors[0] and 'cleanup' in errors[0]
        assert task.closed, 'Expired task must never become usable after cleanup failure'
        assert time.monotonic()-started<1.6
    finally:
        release.set();remove_release.set();thread.join(2)
        if task.timer:task.timer.cancel()
        assert task.cleanup_done.wait(2)


def test_completed_exec_releases_stream_transport():
    from lab.docker_runtime import DockerTask
    docker,c,_=client(inspected());closed=[]
    class Stream:
        def __iter__(self):return iter([(b'hello',b'warning')])
        def close(self):closed.append(True)
    docker.api=SimpleNamespace(exec_create=lambda *a,**kw:{'Id':'exec'},exec_start=lambda *a,**kw:Stream(),exec_inspect=lambda *a:{'Running':False,'ExitCode':0})
    with DockerTask('install','task',client=docker) as task:
        result=task.run(['python','fixture'])
    assert (result.stdout,result.stderr,result.returncode)==('hello','warning',0)
    assert closed==[True]


def test_sdk_socket_stream_cancellation_finishes_async_executor():
    import asyncio
    import socket
    import threading
    import time
    from docker.types.daemon import CancellableStream
    from lab.docker_runtime import DockerTask
    from lab.sdk_builder import bound_session
    docker,c,_=client(inspected());reader,peer=socket.socketpair();finished=threading.Event()
    def frames():
        try:
            while True:
                chunk=reader.recv(1024)
                if not chunk:return
                yield (chunk,None)
        finally:finished.set()
    raw=SimpleNamespace(closed=False,_fp=SimpleNamespace(fp=SimpleNamespace(raw=SimpleNamespace(_sock=reader))))
    stream=CancellableStream(frames(),SimpleNamespace(raw=raw))
    docker.api=SimpleNamespace(exec_create=lambda *a,**kw:{'Id':'exec'},exec_start=lambda *a,**kw:stream,exec_inspect=lambda *a:{'Running':False,'ExitCode':0})
    def failed_remove(**kw):raise RuntimeError('daemon unavailable')
    c.remove=failed_remove
    async def original_stream(**kw):pass
    inner=SimpleNamespace(_stream_into_exec=original_stream)
    try:
        with pytest.raises(ValueError,match='time limit.*cleanup'):
            with DockerTask('install','task',client=docker) as task:
                bound_session(inner,task)
                started=time.monotonic()
                asyncio.run(inner._exec_run(cmd=['python','silent'],workdir=None,user=None,timeout=.05,command_for_errors=(),kill_on_timeout=True))
        assert finished.wait(1) and reader.fileno()==-1
        assert time.monotonic()-started<1.5
    finally:peer.close();reader.close()


def test_explicit_close_cancels_silent_command_without_waiting_for_deadline():
    import threading
    from lab.docker_runtime import DockerTask
    docker,c,_=client(inspected());reading=threading.Event();closed=threading.Event();done=threading.Event();errors=[]
    class Stream:
        def __iter__(self):return self
        def __next__(self):reading.set();closed.wait(2);raise StopIteration
        def close(self):closed.set()
    docker.api=SimpleNamespace(exec_create=lambda *a,**kw:{'Id':'exec'},exec_start=lambda *a,**kw:Stream(),exec_inspect=lambda *a:{'Running':False,'ExitCode':0})
    with DockerTask('install','task',client=docker) as task:
        def execute():
            try:task.run(['python','silent'],timeout=20)
            except ValueError as exc:errors.append(str(exc))
            finally:done.set()
        thread=threading.Thread(target=execute,daemon=True)
        try:
            thread.start();assert reading.wait(1);task.close()
            assert done.wait(.5) and closed.is_set()
            assert len(errors)==1 and 'cancelled' in errors[0]
        finally:closed.set();thread.join(2)


def test_stream_returned_after_timeout_is_still_closed():
    import threading
    from lab.docker_runtime import DockerTask
    docker,c,_=client(inspected());starting=threading.Event();release=threading.Event();closed=threading.Event();done=threading.Event();errors=[]
    class Stream:
        def __iter__(self):return iter([])
        def close(self):closed.set()
    def start(*a,**kw):starting.set();release.wait(2);return Stream()
    docker.api=SimpleNamespace(exec_create=lambda *a,**kw:{'Id':'exec'},exec_start=start,exec_inspect=lambda *a:pytest.fail('Cancelled execution must not inspect/continue'))
    with DockerTask('install','task',client=docker) as task:
        def execute():
            try:task.run(['python','fixture'],timeout=.05)
            except ValueError as exc:errors.append(str(exc))
            finally:done.set()
        thread=threading.Thread(target=execute,daemon=True)
        try:
            thread.start();assert starting.wait(1)
            assert done.wait(.5) and 'time limit' in errors[0]
            release.set();assert closed.wait(1)
        finally:release.set();thread.join(2)


def test_output_overflow_revokes_task_and_closes_stream():
    from lab.docker_runtime import DockerTask
    docker,c,_=client(inspected());closed=[]
    class Stream:
        def __iter__(self):return iter([(b'x'*33,None)])
        def close(self):closed.append(True)
    docker.api=SimpleNamespace(exec_create=lambda *a,**kw:{'Id':'exec'},exec_start=lambda *a,**kw:Stream(),exec_inspect=lambda *a:pytest.fail('Overflow must not continue'))
    with pytest.raises(ValueError,match='output exceeds limit'):
        with DockerTask('install','task',client=docker) as task:task.run(['python','fixture'],output_limit=32)
    assert task.closed and c.removed and closed==[True]
    with pytest.raises(ValueError,match='limit'):task.run(['python','fixture'])
