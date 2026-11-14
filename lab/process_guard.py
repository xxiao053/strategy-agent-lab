"""Windows process-tree cleanup and bounded output for the trusted coding launcher."""
import ctypes
import os
from ctypes import wintypes
import subprocess
import threading
import time


def _start_input(process,data):
    """Feed concurrently so pipe backpressure cannot bypass the supervisor deadline."""
    def write():
        try:
            if data is not None:process.stdin.write(data)
        except (BrokenPipeError,OSError):pass
        finally:
            try:process.stdin.close()
            except (BrokenPipeError,OSError):pass
    writer=threading.Thread(target=write,daemon=True);writer.start()
    return writer


def bounded_run(args,*,input=None,timeout=40,output_limit=2000000,workspace=None,**kwargs):
    if os.name!='nt':return portable_run(args,input=input,timeout=timeout,output_limit=output_limit,workspace=workspace,**kwargs)
    data=None if input is None else input.encode('utf-8')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    class Basic(ctypes.Structure):
        _fields_=[('process_time',ctypes.c_int64),('job_time',ctypes.c_int64),('flags',wintypes.DWORD),
                  ('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),('active',wintypes.DWORD),
                  ('affinity',ctypes.c_size_t),('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
    class IO(ctypes.Structure):_fields_=[(name,ctypes.c_uint64) for name in ['ro','wo','oo','rb','wb','ob']]
    class Extended(ctypes.Structure):
        _fields_=[('basic',Basic),('io',IO),('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),
                  ('peak_process_memory',ctypes.c_size_t),('peak_job_memory',ctypes.c_size_t)]
    kernel.CreateJobObjectW.restype=wintypes.HANDLE
    kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR]
    kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    job=kernel.CreateJobObjectW(None,None)
    if not job:raise ValueError('Cannot establish process cleanup boundary.')
    limits=Extended();limits.basic.flags=0x2000|0x200;limits.job_memory=2*1024**3
    if not kernel.SetInformationJobObject(job,9,ctypes.byref(limits),ctypes.sizeof(limits)):
        kernel.CloseHandle(job);raise ValueError('Cannot apply process resource limits.')
    process=None;readers=[];writer=None
    try:
        process=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                 creationflags=subprocess.CREATE_NO_WINDOW,**kwargs)
        deadline=time.monotonic()+timeout
        # The launched executable is trusted Codex, not user code; attach before supplying its task.
        if not kernel.AssignProcessToJobObject(job,wintypes.HANDLE(int(process._handle))):
            process.kill();process.wait();raise ValueError('Cannot attach coding process to cleanup boundary.')
        output=[bytearray(),bytearray()];overflow=threading.Event();lock=threading.Lock()
        def read(pipe,index):
            while True:
                block=pipe.read(4096)
                if not block:break
                with lock:
                    if sum(map(len,output))+len(block)>output_limit:
                        overflow.set();break
                    output[index].extend(block)
        for index,pipe in enumerate([process.stdout,process.stderr]):
            t=threading.Thread(target=read,args=(pipe,index),daemon=True);t.start();readers.append(t)
        writer=_start_input(process,data)
        while process.poll() is None:
            if workspace:
                from .project_evaluator import bounded_inventory
                bounded_inventory(workspace)
            if overflow.is_set():raise ValueError('Process output exceeded the capture limit.')
            if time.monotonic()>deadline:raise subprocess.TimeoutExpired(args,timeout)
            time.sleep(.03)
        for t in readers:t.join(timeout=.5)
        if overflow.is_set():raise ValueError('Process output exceeded the capture limit.')
        return subprocess.CompletedProcess(args,process.returncode,*[bytes(x).decode('utf-8','replace') for x in output])
    finally:
        kernel.CloseHandle(job)  # KILL_ON_JOB_CLOSE also stops descendants after normal completion.
        if process is not None:
            process.wait(timeout=5)
            if writer:writer.join(timeout=1)
            for t in readers:t.join(timeout=1)
            process.stdout.close();process.stderr.close()


def portable_run(args,*,input=None,timeout=40,output_limit=2000000,workspace=None,**kwargs):
    """Trusted controller commands only; generated code still requires Docker."""
    import signal
    data=None if input is None else input.encode('utf-8')
    process=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,**kwargs)
    deadline=time.monotonic()+timeout;writer=None
    output=[bytearray(),bytearray()];overflow=threading.Event();lock=threading.Lock();readers=[]
    def read(pipe,index):
        while True:
            block=pipe.read(4096)
            if not block:break
            with lock:
                if sum(map(len,output))+len(block)>output_limit:overflow.set();break
                output[index].extend(block)
    try:
        for index,pipe in enumerate((process.stdout,process.stderr)):
            thread=threading.Thread(target=read,args=(pipe,index),daemon=True);thread.start();readers.append(thread)
        writer=_start_input(process,data)
        while process.poll() is None:
            if workspace:
                from .project_evaluator import bounded_inventory
                bounded_inventory(workspace)
            if overflow.is_set():raise ValueError('Process output exceeded the capture limit.')
            if time.monotonic()>deadline:raise subprocess.TimeoutExpired(args,timeout)
            time.sleep(.03)
        for thread in readers:thread.join(.5)
        if overflow.is_set():raise ValueError('Process output exceeded the capture limit.')
        return subprocess.CompletedProcess(args,process.returncode,*[bytes(x).decode('utf-8','replace') for x in output])
    finally:
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        process.wait(timeout=5)
        if writer:writer.join(timeout=1)
        for thread in readers:thread.join(1)
        process.stdout.close();process.stderr.close()
