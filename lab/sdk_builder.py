"""Pinned Agents SDK orchestration; its tools only reach a hardened task container."""
import asyncio
import hashlib
import importlib.metadata
import inspect
import io
import json
import math
import shlex
from pathlib import Path
import httpx
from .docker_runtime import DockerTask,WORKER_IMAGE,installation_id
from .docker_policy import USER
from .sdk_budget import BudgetTransport,MAX_CONSTRUCTION_REQUESTS

MAX_CONSTRUCTION_TOOLS=100


def path_helper():
    from agents.sandbox.session.runtime_helpers import RESOLVE_WORKSPACE_PATH_HELPER as helper
    if (helper.name!='resolve-workspace-path' or
        str(helper.install_path)!='/tmp/openai-agents/bin/resolve-workspace-path-62a6e78539cf' or
        not isinstance(helper.content,str) or
        hashlib.sha256(helper.content.encode()).hexdigest()!='62a6e78539cfbc109e225312d0c42dee905852c405a6a929cf83a084ca44b5b9'):
        raise ValueError('Unsupported SDK path helper contract; install the pinned distribution dependencies.')
    return helper


def sdk_contract():
    from agents import ModelSettings
    from agents.retry import ModelRetrySettings
    from agents.sandbox.sandboxes.docker import DockerSandboxClient,DockerSandboxSession
    from openai import AsyncOpenAI
    version=importlib.metadata.version('openai-agents')
    expected={'self','image','manifest','exposed_ports','network_mode','session_id','labels'}
    if version!='0.24.0' or set(inspect.signature(DockerSandboxClient._create_container).parameters)!=expected:
        raise ValueError('Unsupported Agents SDK contract; install the pinned distribution dependencies.')
    if set(inspect.signature(DockerSandboxSession._exec_run).parameters)!={'self','cmd','workdir','user','timeout','command_for_errors','kill_on_timeout'} or set(inspect.signature(DockerSandboxSession._stream_into_exec).parameters)!={'self','cmd','stream','error_path','user'}:
        raise ValueError('Unsupported SDK execution contract.')
    path_helper()
    settings=ModelSettings(retry=ModelRetrySettings(max_retries=0))
    # Validate accepted constructor options without allocating an unowned HTTP pool.
    inspect.signature(AsyncOpenAI).bind(api_key='controller-managed',max_retries=0)
    return dict(version=version,runner_retries=settings.retry.max_retries,client_retries=0,tracing=False,max_turns=MAX_CONSTRUCTION_REQUESTS)


def close_after_error(task,error):
    try:task.close()
    except Exception as cleanup:error.add_note(str(cleanup))


async def task_exec(task,cmd,**limits):
    try:return await asyncio.to_thread(task.run,cmd,**limits)
    except asyncio.CancelledError as error:
        close_after_error(task,error);raise


def bound_session(inner,task):
    """Narrow pinned hooks cover SDK helper/patch execution, not just model shell tools."""
    from agents.sandbox import ExecResult
    async def execute(*,cmd,workdir,user,timeout,command_for_errors,kill_on_timeout):
        if user not in (None,'',USER):raise ValueError('SDK cannot elevate the task user.')
        if workdir not in (None,'/workspace'):raise ValueError('Unsupported SDK working directory.')
        if timeout is not None and (isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not math.isfinite(timeout) or timeout<=0):
            raise ValueError('Unsupported SDK timeout.')
        helper=path_helper()
        if cmd and cmd[0]==str(helper.install_path):
            if len(cmd)!=4 or cmd[1]!='/workspace' or cmd[3] not in {'0','1','2'}:
                raise ValueError('Unsupported SDK path helper scope.')
            # Execute trusted pinned content, never the task-writable /tmp copy.
            # Positional arguments retain SDK path validation without changing noexec.
            cmd=['/bin/sh','-c',helper.content,*cmd]
        result=await task_exec(task,cmd,timeout=min(timeout if timeout is not None else 20,20),output_limit=65536)
        return ExecResult(stdout=result.stdout.encode(),stderr=result.stderr.encode(),exit_code=result.returncode)
    original=inner._stream_into_exec
    async def stream_into(*,cmd,stream,error_path,user=None):
        if user not in (None,'',USER):raise ValueError('SDK cannot elevate the task user.')
        content=stream.read(256001)
        if isinstance(content,str):content=content.encode()
        if len(content)>256000:raise ValueError('SDK file write exceeds limit.')
        try:await asyncio.wait_for(original(cmd=cmd,stream=io.BytesIO(content),error_path=error_path,user=USER),20)
        except BaseException as error:close_after_error(task,error);raise
    inner._exec_run=execute
    inner._stream_into_exec=stream_into
    inner.supports_pty=lambda:False


def hardened_client(task):
    from agents.sandbox.sandboxes.docker import DockerSandboxClient
    class HardenedClient(DockerSandboxClient):
        def _wrap_session(self,inner,*,instrumentation=None):
            bound_session(inner,task)
            return super()._wrap_session(inner,instrumentation=instrumentation)
        async def _create_container(self,image,*,manifest=None,exposed_ports=(),network_mode=None,session_id=None,labels=None):
            if image!=WORKER_IMAGE or exposed_ports or network_mode!='none':raise ValueError('Unsupported SDK container request.')
            if manifest is None or manifest.root!='/workspace' or manifest.entries or manifest.users or manifest.groups or manifest.extra_path_grants or await manifest.environment.resolve():
                raise ValueError('SDK manifest authority is not permitted.')
            task.inspect()
            return task.container
    return HardenedClient(task.client)


async def construct(task,prompt,transport,cfg):
    sdk_contract()
    from agents import Runner,RunConfig,ModelSettings,set_tracing_disabled
    from agents.retry import ModelRetrySettings
    from agents.models.openai_responses import OpenAIResponsesModel
    from agents.sandbox import SandboxAgent,Manifest,SandboxRunConfig,SandboxArchiveLimits
    from agents.sandbox.capabilities import Shell,Filesystem
    from agents.sandbox.sandboxes.docker import DockerSandboxClientOptions
    from agents.sandbox.snapshot import NoopSnapshotSpec
    from agents.sandbox.errors import ApplyPatchDiffError,ApplyPatchFileNotFoundError
    from openai import AsyncOpenAI
    from openai.types.shared import Reasoning
    set_tracing_disabled(True)
    rounds=0
    def shell_tools(bundle):
        bundle.write_stdin=None
        async def execute(context,arguments):
            nonlocal rounds
            rounds+=1
            if rounds>MAX_CONSTRUCTION_TOOLS:raise ValueError('Construction tool limit reached.')
            body=json.loads(arguments)
            if body.get('tty'):raise ValueError('Interactive processes are not supported.')
            cwd=body.get('workdir') or '/workspace'
            if cwd!='/workspace' and not cwd.startswith('/workspace/'):raise ValueError('Unsupported command directory.')
            command='cd '+shlex.quote(cwd)+' && '+body['cmd']
            result=await task_exec(task,['sh','-c',command],timeout=20)
            return f'Exit code: {result.returncode}\n{result.stdout}\n{result.stderr}'
        bundle.exec_command.on_invoke_tool=execute
    def filesystem_tools(bundle):
        for tool in (bundle.view_image,bundle.apply_patch):
            original=tool.on_invoke_tool
            async def invoke(context,arguments,_original=original):
                nonlocal rounds
                rounds+=1
                if rounds>MAX_CONSTRUCTION_TOOLS or len(str(arguments).encode())>180000:raise ValueError('Construction tool limit reached.')
                task.inspect()
                try:result=await asyncio.wait_for(_original(context,arguments),timeout=20)
                except (ApplyPatchDiffError,ApplyPatchFileNotFoundError):
                    task.inspect()
                    return ('Patch did not complete: file content or patch format did not match. '
                        'The workspace may contain partial edits. Read the affected files, then correct '
                        'the patch. This does not change the method, permissions or remaining limits.')
                except BaseException as error:close_after_error(task,error);raise
                if len(str(result).encode())>65536:raise ValueError('Tool output exceeds limit.')
                return result
            tool.on_invoke_tool=invoke
    client=hardened_client(task)
    # Runner-owned sessions are stopped/deleted at turn end. Borrow our live task
    # instead, so bounded collection occurs before the task context destroys tmpfs.
    session=await client.create(manifest=Manifest(),snapshot=NoopSnapshotSpec(),
        options=DockerSandboxClientOptions(image=WORKER_IMAGE,network_mode='none'))
    await session.start()
    async with httpx.AsyncClient(transport=transport,timeout=120,follow_redirects=False) as http:
        model_client=AsyncOpenAI(api_key='controller-managed',max_retries=0,http_client=http)
        # DockerTask fixes all exec/stream identities; SDK run_as would provision an account.
        agent=SandboxAgent(name='Method builder',instructions=prompt,run_as=None,default_manifest=Manifest(),
            capabilities=[Shell(configure_tools=shell_tools),Filesystem(configure_tools=filesystem_tools)],
            model=OpenAIResponsesModel(cfg['model'],model_client),
            model_settings=ModelSettings(parallel_tool_calls=False,max_tokens=6000,store=False,retry=ModelRetrySettings(max_retries=0),timeout=120,
                reasoning=Reasoning(effort=cfg['reasoning_effort']) if cfg.get('reasoning_effort') else None))
        start=(f'Implement the approved project and verify it. You start in /workspace. '
            'Python and POSIX sh/find are available; rg is not installed. '
            'The trusted inputs are method.json, EXECUTION-CONTRACT.md and, when material is selected, '
            'MATERIAL-INDEX.json with the complete indexed text views. Check those exact paths with Python; '
            'do not search parent directories or rediscover the environment. '
            'If BUILD-CONTEXT.json exists, prior code is already present as an untrusted starting point. '
            'Read that context and the relevant existing files, run their tests, then make focused repairs '
            'instead of recreating the project. Failed-attempt code is unverified. '
            'Only the current approved method and trusted contract define the requirements. '
            f'The complete run has at most {MAX_CONSTRUCTION_REQUESTS} model requests. '
            'Avoid empty commands; batch related file edits and reserve requests for tests, fixes and the final summary.')
        result=await asyncio.wait_for(Runner.run(agent,start,max_turns=MAX_CONSTRUCTION_REQUESTS,
            run_config=RunConfig(tracing_disabled=True,sandbox=SandboxRunConfig(session=session,
                archive_limits=SandboxArchiveLimits(max_input_bytes=2500000,max_extracted_bytes=2500000,max_members=512)))),timeout=480)
        return str(result.final_output)[:24000]


def verify_saved_project(work,version,contract,owner):
    from .materials import verify_reference_inputs,read_project_text
    from .build_runtime import verify_project
    from .execution_contract import verify_execution_contract
    from .project_evaluator import bounded_inventory
    if (work/'BLOCKED.md').exists():raise ValueError('Builder found a blocking method decision. Clarify before rebuilding.')
    verify_reference_inputs(work,version)
    if (work/'EXECUTION-CONTRACT.md').read_text(encoding='utf-8')!=contract:raise ValueError('Trusted execution contract changed.')
    # Each independent command gets a fresh worker; generated source never runs here.
    def isolated(args):
        current={p.relative_to(work).as_posix():read_project_text(p) for p,is_dir,_ in bounded_inventory(work) if not is_dir}
        with DockerTask(owner,wall_seconds=45) as verification:
            verification.seed(current);verification.probe();result=verification.run(args,timeout=30)
            after=verification.collect()
        if {a['name']:a['text'] for a in after if a['name']!='result.json'}!={k:v for k,v in current.items() if k!='result.json'}:
            raise ValueError('Independent verification changed protected source.')
        for a in after:
            if a['name']=='result.json':(work/'result.json').write_text(a['text'],encoding='utf-8')
        return result
    validation=verify_project(work,version['method'],isolated)
    if validation['tests_passed'] and not validation['demo_exit']:
        validation.update(verify_execution_contract(work,version['method'],isolated))
    verify_reference_inputs(work,version)
    return validation


def run_build(builder,pid,bid,version,cfg,key,budget,prompt):
    from .materials import construction_inputs
    from .build_runtime import collect_artifacts
    from .execution_contract import seal_build
    folder=builder.store.path.parent/'builds'/pid/bid;work=folder/'project'
    def save_artifacts(artifacts,destination=work):
        for artifact in artifacts:
            dest=destination/artifact['name'];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(artifact['text'],encoding='utf-8',newline='')
    try:
        work.mkdir(parents=True)
        contract=(Path(__file__).resolve().parents[1]/'docs/en/execution-contract.md').read_text(encoding='utf-8')
        inputs=construction_inputs(version,contract)
        prior=next((b for b in reversed(builder.store.get(pid).get('builds',[]))
            if b['id']!=bid and (b['status']=='completed' or (b['status']=='failed' and b['version']==version['version']))
            and any(a['name']=='strategy.py' for a in b.get('artifacts',[]))),None)
        if prior:
            # Reuse source as untrusted editing material, never old approvals,
            # material copies, test outcomes or execution seals.
            reused={a['name']:a['text'] for a in prior['artifacts']
                if (a['name'].endswith('.py') or a['name'] in {'execution.json','README.md'})
                and a['name'] not in inputs}
            inputs.update(reused)
            inputs['BUILD-CONTEXT.json']=json.dumps({'build_id':prior['id'],'version':prior['version'],
                'status':prior['status'],'files':sorted(reused),'verified_for_current_method':False})
        else:
            from .example_copy import starter_artifacts
            seed=starter_artifacts(builder.store.get(pid))
            inputs.update({a['name']:a['text'] for a in seed if a['name'] not in inputs})
            if seed:inputs['BUILD-CONTEXT.json']=json.dumps({'source':'included example','files':[a['name'] for a in seed],'verified_for_current_method':False})
        owner=installation_id(builder.store.path.parent)
        required={'strategy.py','execution.json','test_strategy.py','demo.py','README.md'}
        if (prior and prior['status']=='failed' and prior['version']==version['version']
            and not next(b for b in builder.store.get(pid)['builds'] if b['id']==bid).get('repair_notes')
            and required.issubset(inputs) and not any(a['name']=='BLOCKED.md' for a in prior['artifacts'])):
            # Validate a copy before spending to repair it. A failed final agent turn
            # need not discard otherwise complete code; prior status is never rewritten.
            saved_check=folder/'saved-check';saved_check.mkdir()
            with DockerTask(owner,bid+'-saved') as staging:
                staging.seed(inputs);staging.probe();save_artifacts(staging.collect(),saved_check)
            validation=verify_saved_project(saved_check,version,contract,owner)
            if validation['tests_passed'] and not validation['demo_exit']:
                artifacts=collect_artifacts(saved_check)
                save_artifacts(artifacts)
                builder.update(pid,bid,status='completed',artifacts=artifacts,validation=validation,
                    execution_hash=seal_build(artifacts,version['method']),verification_only=True,
                    recovered_from=prior['id'],model=prior.get('model'),provider=prior.get('provider'),
                    connection_id=prior.get('connection_id'),events=[{'type':'summary','text':
                        'Saved code from the previous attempt passed fresh independent verification. No new model requests.'}])
                return
        with DockerTask(owner,bid) as task:
            task.seed(inputs);task.probe()
            transport=BudgetTransport(builder.store,builder.connections,pid,cfg,key,budget,bid,check_task=task.inspect)
            try:
                summary=asyncio.run(construct(task,prompt,transport,cfg))
            except Exception:
                # Collect only through the existing bounded archive/link validator,
                # before disposable resources are removed. Never execute this output.
                try:save_artifacts(task.collect())
                except Exception:pass  # Preserve the original failure if collection is unsafe/unavailable.
                raise
            save_artifacts(task.collect())
        builder.update(pid,bid,events=[{'type':'summary','text':summary}])
        validation=verify_saved_project(work,version,contract,owner)
        builder.update(pid,bid,validation=validation)
        if not validation['tests_passed'] or validation['demo_exit']:raise ValueError('Independent verification failed.')
        artifacts=collect_artifacts(work)
        builder.update(pid,bid,status='completed',artifacts=artifacts,validation=validation,execution_hash=seal_build(artifacts,version['method']),events=[{'type':'summary','text':summary}])
        builder.connections.construction_observed(cfg['id'],generation=cfg.get('generation',1))
    except Exception as exc:
        from agents.exceptions import MaxTurnsExceeded
        if isinstance(exc,MaxTurnsExceeded):
            message=f'Construction reached its {MAX_CONSTRUCTION_REQUESTS}-turn limit before completion. Inspect any saved partial files; they are not verified. No automatic retry.'
        elif isinstance(exc,TimeoutError):
            message='Construction exceeded its time limit. Inspect any saved partial files; they are not verified. No automatic retry.'
        else:
            message=str(exc) if isinstance(exc,ValueError) else 'Docker construction runtime failed. Inspect any saved partial files; they are not verified. No automatic retry.'
        try:artifacts=collect_artifacts(work)
        except (ValueError,OSError):artifacts=[]
        builder.update(pid,bid,status='failed',error=message,artifacts=artifacts)
    finally:builder.store.mutate(pid,lambda p:p.update(busy=False))
