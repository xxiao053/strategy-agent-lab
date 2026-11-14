import copy
import io
import tarfile
import pytest


def test_create_has_no_authority_or_unbounded_storage():
    from lab.docker_policy import create_options, validate_inspect
    opts=create_options('sha256:reviewed','install','task')
    assert opts['network_mode']=='none' and opts['user']=='10001:10001'
    assert opts['cap_drop']==['ALL'] and opts['read_only'] is True
    assert opts['security_opt']==['no-new-privileges:true']
    assert not any(k in opts for k in ('ports','volumes','devices','cap_add'))
    assert opts['mem_limit']==268435456 and opts['pids_limit']==64 and opts['nano_cpus']==1000000000
    assert 'size=16777216' in opts['tmpfs']['/workspace']
    assert not any('KEY' in k or 'TOKEN' in k for k in opts['environment'])


def inspected():
    return dict(Config=dict(User='10001:10001',Env=['PATH=/usr/local/bin:/usr/bin:/bin','HOME=/tmp','PYTHONDONTWRITEBYTECODE=1'],Labels={'lab.installation':'install','lab.task':'task'},Image='sha256:reviewed',ExposedPorts=None),
      HostConfig=dict(NetworkMode='none',Privileged=False,ReadonlyRootfs=True,CapDrop=['ALL'],CapAdd=None,SecurityOpt=['no-new-privileges:true'],Memory=268435456,MemorySwap=268435456,NanoCpus=1000000000,PidsLimit=64,PortBindings={},Binds=None,Devices=[],PidMode='',IpcMode='private',Tmpfs={'/workspace':'rw,nosuid,nodev,size=16777216,nr_inodes=512,uid=10001,gid=10001,mode=700','/tmp':'rw,nosuid,nodev,size=8388608,nr_inodes=256,mode=1777'},LogConfig={'Type':'none','Config':{}},Mounts=[]),
      Mounts=[],NetworkSettings={'Networks':{'none':{}},'Ports':{}})


@pytest.mark.parametrize('section,key,value',[
 ('HostConfig','NetworkMode','bridge'),('Config','User','root'),('HostConfig','CapAdd',['SYS_ADMIN']),
 ('HostConfig','ReadonlyRootfs',False),('HostConfig','Memory',0),('HostConfig','SecurityOpt',['seccomp=unconfined']),
 ('HostConfig','Binds',['/:/host']),('Config','Env',['OPENAI_API_KEY=secret']),('HostConfig','PidsLimit',0),
 ('HostConfig','Tmpfs',{'/workspace':'rw,size=999999999'}),('HostConfig','Privileged',True)])
def test_inspection_rejects_tampering(section,key,value):
    from lab.docker_policy import validate_inspect
    attrs=inspected();validate_inspect(attrs,'sha256:reviewed','install','task')
    attrs[section][key]=value
    with pytest.raises(ValueError,match='policy'):validate_inspect(attrs,'sha256:reviewed','install','task')


@pytest.mark.parametrize('name,kind,size',[('../escape.py',tarfile.REGTYPE,1),('project/link.py',tarfile.SYMTYPE,0),('project/big.py',tarfile.REGTYPE,256001),('project/dev',tarfile.CHRTYPE,0),('workspace/CON.py',tarfile.REGTYPE,1),('workspace/dir./x.py',tarfile.REGTYPE,1),('foreign/file.py',tarfile.REGTYPE,1)])
def test_archive_collection_rejects_unsafe_output(name,kind,size):
    from lab.docker_policy import unpack_artifacts
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w') as tar:
        entry=tarfile.TarInfo(name);entry.type=kind;entry.size=size;entry.linkname='/etc/passwd'
        tar.addfile(entry,io.BytesIO(b'x'*size) if kind==tarfile.REGTYPE else None)
    with pytest.raises(ValueError):unpack_artifacts([stream.getvalue()])


def test_collection_keeps_only_bounded_regular_files():
    from lab.docker_policy import unpack_artifacts
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w') as tar:
        entry=tarfile.TarInfo('workspace/strategy.py');entry.size=4;tar.addfile(entry,io.BytesIO(b'pass'))
    assert unpack_artifacts([stream.getvalue()])==[{'name':'strategy.py','text':'pass'}]


def test_readonly_volume_cannot_be_replaced_by_bind_or_writable_mount():
    from lab.docker_policy import validate_inspect
    attrs=inspected();attrs['HostConfig']['Tmpfs'].pop('/workspace')
    attrs['Mounts']=[{'Type':'volume','Name':'task-volume','Destination':'/workspace','RW':False}]
    validate_inspect(attrs,'sha256:reviewed','install','task',volume='task-volume',readonly=True)
    attrs['Mounts'][0]['RW']=True
    with pytest.raises(ValueError):validate_inspect(attrs,'sha256:reviewed','install','task',volume='task-volume',readonly=True)
    attrs['Mounts'][0].update(RW=False,Type='bind')
    with pytest.raises(ValueError):validate_inspect(attrs,'sha256:reviewed','install','task',volume='task-volume',readonly=True)


def test_archive_rejects_case_collisions_before_windows_collection():
    from lab.docker_policy import unpack_artifacts
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w') as tar:
        for name in ('workspace/method.json','workspace/METHOD.JSON'):
            entry=tarfile.TarInfo(name);entry.size=2;tar.addfile(entry,io.BytesIO(b'{}'))
    with pytest.raises(ValueError,match='Duplicate'):unpack_artifacts([stream.getvalue()])


@pytest.mark.parametrize('extra',[
    {'Type':'bind','Source':'/host','Destination':'/extra','RW':True},
    {'Type':'tmpfs','Destination':'/extra','RW':True},
    {'Type':'volume','Name':'foreign','Destination':'/extra','RW':True},
])
def test_owned_workspace_rejects_unexpected_mounts(extra):
    from lab.docker_policy import validate_inspect
    attrs=inspected();attrs['HostConfig']['Tmpfs'].pop('/workspace')
    attrs['Mounts']=[{'Type':'volume','Name':'owned','Destination':'/workspace','RW':True},extra]
    with pytest.raises(ValueError,match='policy'):validate_inspect(attrs,'sha256:reviewed','install','task',volume='owned')
