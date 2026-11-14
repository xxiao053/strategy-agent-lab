"""Fail-closed task-container policy; Docker authority belongs only to the controller."""
import io
import re
import tarfile
from pathlib import PurePosixPath
from .project_limits import DECISION_INPUT_BYTES

USER='10001:10001'
LABEL='lab.installation'
ENV={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp','PYTHONDONTWRITEBYTECODE':'1'}
WORK_TMPFS='rw,nosuid,nodev,size=16777216,nr_inodes=512,uid=10001,gid=10001,mode=700'
TMP_TMPFS='rw,nosuid,nodev,size=8388608,nr_inodes=256,mode=1777'
SUFFIXES={'.py','.md','.json','.csv','.txt'}


def create_options(image,installation,task,*,volume=None,readonly=False):
    options=dict(image=image,entrypoint=['tail'],command=['-f','/dev/null'],detach=True,
        user=USER,working_dir='/workspace',environment=dict(ENV),network_mode='none',
        privileged=False,cap_drop=['ALL'],security_opt=['no-new-privileges:true'],read_only=True,
        mem_limit=268435456,memswap_limit=268435456,nano_cpus=1000000000,pids_limit=64,
        ipc_mode='private',tmpfs={'/tmp':TMP_TMPFS},log_config={'type':'none'},
        labels={LABEL:installation,'lab.task':task})
    if volume:
        options['mounts']=[{'Type':'volume','Source':volume,'Target':'/workspace','ReadOnly':readonly}]
    else:options['tmpfs']['/workspace']=WORK_TMPFS
    return options


def validate_inspect(attrs,image,installation,task,*,volume=None,readonly=False,image_env=()):
    def require(ok):
        if not ok:raise ValueError('Docker task policy verification failed; no workload permitted.')
    c=attrs.get('Config',{});h=attrs.get('HostConfig',{});n=attrs.get('NetworkSettings',{})
    expected=create_options(image,installation,task,volume=volume,readonly=readonly)
    require(c.get('User')==USER and c.get('Image')==image and c.get('Labels',{}).get(LABEL)==installation and c.get('Labels',{}).get('lab.task')==task)
    require(h.get('NetworkMode')=='none' and not set(n.get('Networks',{}))-{'none'})
    require(not c.get('ExposedPorts') and not h.get('PortBindings') and not n.get('Ports'))
    for key,value in dict(Privileged=False,ReadonlyRootfs=True,Memory=268435456,MemorySwap=268435456,NanoCpus=1000000000,PidsLimit=64,IpcMode='private').items():require(h.get(key)==value)
    require(h.get('CapDrop')==['ALL'] and not h.get('CapAdd'))
    require(h.get('SecurityOpt') in (['no-new-privileges:true'],['no-new-privileges']))
    require(not h.get('Binds') and not h.get('Devices') and not h.get('DeviceRequests') and not h.get('PidMode'))
    require(h.get('Tmpfs')==expected['tmpfs'] and h.get('LogConfig',{}).get('Type')=='none')
    env=dict(item.split('=',1) for item in image_env)
    env.update(ENV)
    require(dict(item.split('=',1) for item in c.get('Env',[]))==env)
    mounts=[m for m in attrs.get('Mounts',[]) if m.get('Type')!='tmpfs']
    tmp_mounts=[m.get('Destination') for m in attrs.get('Mounts',[]) if m.get('Type')=='tmpfs']
    require(len(tmp_mounts)==len(set(tmp_mounts)) and set(tmp_mounts)<=set(expected['tmpfs']))
    if volume:
        require(len(mounts)==1 and mounts[0].get('Type')=='volume' and mounts[0].get('Name')==volume and mounts[0].get('Destination')=='/workspace' and mounts[0].get('RW') is not readonly)
    else:require(not mounts and not h.get('Mounts'))


def safe_name(name):
    p=PurePosixPath(name)
    reserved={'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}
    if not re.fullmatch(r'[A-Za-z0-9_./-]{1,180}',name) or p.is_absolute() or any(s in {'','..','.'} or s.endswith('.') or s.split('.')[0].upper() in reserved for s in name.split('/')) or len(p.parts)>8:
        raise ValueError('Unsafe task artifact path.')
    return p


def pack_files(files):
    stream=io.BytesIO();total=0
    if len(files)>80:raise ValueError('Too many task inputs.')
    with tarfile.open(fileobj=stream,mode='w') as tar:
        for name,text in files.items():
            safe_name(name);raw=text if isinstance(text,bytes) else text.encode()
            if name!='context.json':total+=len(raw)
            if len(raw)>(DECISION_INPUT_BYTES if name=='context.json' else 1500000) or total>2500000:
                raise ValueError('Task input exceeds limit.')
            entry=tarfile.TarInfo(name);entry.size=len(raw);entry.uid=10001;entry.gid=10001;entry.mode=0o600
            tar.addfile(entry,io.BytesIO(raw))
    return stream.getvalue()


def unpack_artifacts(chunks):
    raw=bytearray()
    for chunk in chunks:
        if len(raw)+len(chunk)>4000000:raise ValueError('Task archive exceeds limit.')
        raw.extend(chunk)
    result=[];total=0;seen=set()
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as tar:
        for index,entry in enumerate(tar):
            if index>=512:raise ValueError('Too many task entries.')
            p=safe_name(entry.name.rstrip('/') if entry.isdir() else entry.name)
            if p.parts[0]!='workspace':raise ValueError('Invalid task archive root.')
            if not entry.isdir() and not entry.isreg():raise ValueError('Task links/devices are forbidden.')
            if entry.size>256000:raise ValueError('Task file exceeds limit.')
            total+=entry.size
            if total>1000000:raise ValueError('Task outputs exceed limit.')
            if entry.isdir():continue
            if len(p.parts)<2:raise ValueError('Invalid task archive root.')
            name=PurePosixPath(*p.parts[1:]).as_posix()
            if name.lower() in seen:raise ValueError('Duplicate task output.')
            seen.add(name.lower())
            if p.suffix not in SUFFIXES or '__pycache__' in p.parts or name=='previous-version.txt':continue
            if len(result)>=80:raise ValueError('Too many task artifacts.')
            result.append(dict(name=name,text=tar.extractfile(entry).read(entry.size+1).decode('utf-8')))
    return result
