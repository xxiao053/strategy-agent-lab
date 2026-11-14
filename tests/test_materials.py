"""Harmless material fixtures; external-network guard remains active."""
import hashlib
import io
import json
import subprocess
import sys
import pytest
from fastapi.testclient import TestClient
from lab.api import create_app
from lab.workspace_store import WorkspaceStore

HEAD={'X-Lab-Request':'1'}

def pdf(text='Buy after review',pages=1,encrypted=False):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject,NameObject,DictionaryObject
    writer=PdfWriter()
    for _ in range(pages):
        page=writer.add_blank_page(width=200,height=200)
        if text:
            font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
            page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
            stream=DecodedStreamObject();stream.set_data(('BT /F1 12 Tf 10 100 Td ('+text+') Tj ET').encode())
            page[NameObject('/Contents')]=writer._add_object(stream)
        else:
            image=DecodedStreamObject();image.set_data(b'\xff\xff\xff')
            from pypdf.generic import NumberObject
            image.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Image'),NameObject('/Width'):NumberObject(1),NameObject('/Height'):NumberObject(1),NameObject('/ColorSpace'):NameObject('/DeviceRGB'),NameObject('/BitsPerComponent'):NumberObject(8)})
            page[NameObject('/Resources')]=DictionaryObject({NameObject('/XObject'):DictionaryObject({NameObject('/Im0'):writer._add_object(image)})})
            stream=DecodedStreamObject();stream.set_data(b'q 50 0 0 50 20 20 cm /Im0 Do Q')
            page[NameObject('/Contents')]=writer._add_object(stream)
    if encrypted:writer.encrypt('private')
    out=io.BytesIO();writer.write(out);return out.getvalue()

@pytest.fixture
def materials(tmp_path,monkeypatch):
    from lab.materials import Materials
    # Format tests exercise real parser, substituting only unavailable OS isolation.
    class FixtureBoundary:
        def __init__(self,work,home):self.work=work
        def probe(self):pass
        def run(self,args,**kwargs):return subprocess.run(args,cwd=self.work,capture_output=True,text=True,encoding='utf-8',timeout=10)
    monkeypatch.setattr('lab.materials.boundary_factory',FixtureBoundary)
    store=WorkspaceStore(tmp_path/'runs/state.sqlite3');p=store.create('Notes','en')
    return Materials(tmp_path,store),store,p['id']

@pytest.mark.parametrize('name,mime,raw,locations,expected',[
    ('notes.txt','text/plain',b'first\n\n<script>alert(1)</script>', ['L1','L2','L3'],'<script>alert(1)</script>'),
    ('notes.md','text/markdown',b'# Rules\nBuy after review', ['L1','L2'],'Buy after review'),
    ('trades.csv','text/csv',b'date,ticker,quantity\n01/02/24,SPY,10', ['R1','R2'],'quantity'),
    ('notes.pdf','application/pdf',None,['P1'],'Buy after review'),
],ids=['text','markdown','csv','pdf'])
def test_preview_preserves_locations_and_private_identity(materials,name,mime,raw,locations,expected):
    m,s,pid=materials;raw=pdf() if raw is None else raw
    saved=m.upload(pid,name,mime,raw)
    assert saved['sha256']==hashlib.sha256(raw).hexdigest()
    content=m.get(pid,saved['id'])
    assert [u['location'] for u in content['units']]==locations
    assert expected in json.dumps(content)
    assert 'path' not in json.dumps(content) and 'original' not in content
    assert s.get(pid)['records']==[]
    other=s.create('Other','en')
    with pytest.raises(KeyError):m.get(other['id'],saved['id'])
    assert m.list(other['id'])==[]

@pytest.mark.parametrize('name,mime,raw,message',[
    ('../notes.txt','text/plain',b'x','filename'),('x.html','text/html',b'<script>','format'),
    ('x.txt','application/pdf',b'%PDF-','type'),('x.pdf','application/pdf',b'broken','PDF'),
    ('x.txt','text/plain',b'\xff','UTF-8'),('x.txt','text/plain',b'x'*512001,'512'),
    ('x.csv','text/csv',b'a\n'+b'x\n'*1001,'rows'),
    ('x.pdf','application/pdf',b'%PDF-'+b'x'*512000,'512'),
    ('x.txt','text/plain',b'x\n'*10001,'lines'),
    ('x.txt','text/plain',b'x'*100001,'characters'),
    ('x.csv','text/csv',b','.join([b'x']*51),'columns'),
    ('x.txt','text/plain',b'%PDF-1.7','type'),
    ('x.csv','text/csv',b'a\n"broken','parsed'),
    ('x.txt','text/plain',b'\0data','Binary'),
],ids=['traversal','html','mime','broken','encoding','bytes','rows','pdf-bytes','lines','characters','columns','signature','csv-broken','binary'])
def test_invalid_material_is_safe_and_not_saved(materials,name,mime,raw,message):
    m,s,pid=materials
    with pytest.raises(ValueError,match=message):m.upload(pid,name,mime,raw)
    assert m.list(pid)==[]

@pytest.mark.parametrize('raw,message',[(lambda:pdf(''),'OCR'),(lambda:pdf(encrypted=True),'encrypted'),(lambda:pdf(pages=101),'pages')])
def test_pdf_limits_and_actionable_errors(materials,raw,message):
    m,s,pid=materials
    with pytest.raises(ValueError,match=message):m.upload(pid,'x.pdf','application/pdf',raw())
    assert m.list(pid)==[]

def test_selection_freezes_source_text_and_rejects_cross_project_or_hash(materials):
    from lab.materials import merge_sources,reference_inputs,verify_reference_inputs
    m,s,pid=materials;a=m.upload(pid,'ref.txt','text/plain',b'ratio = 0.125\nExit after review')
    refs=[{'id':a['id'],'sha256':a['sha256'],'locations':['L1']}]
    frozen=m.select(pid,refs)
    assert frozen[0]['units']==[{'location':'L1','text':'ratio = 0.125'}]
    s.mutate(pid,lambda p:p.update(revision=1,draft={'scope':'x','rules':[{'topic':'ratio','rule':'Use ratio','source':f"material:{a['id']}:L1"}],'questions':[],'material_sources':frozen}))
    approved=s.approve(pid,1)['versions'][0]
    m.upload(pid,'ref.txt','text/plain',b'ratio = 99')
    assert s.get(pid)['versions'][0]==approved
    inputs=reference_inputs(approved)
    assert 'ratio = 0.125' in inputs['MATERIAL-REFERENCES.json']
    assert 'untrusted' in inputs['MATERIAL-REFERENCES.json']
    for name,text in inputs.items():(m.root/name).write_text(text,encoding='utf-8',newline='')
    verify_reference_inputs(m.root,approved)
    (m.root/'MATERIAL-REFERENCES.json').write_text('{}')
    with pytest.raises(ValueError,match='material'):verify_reference_inputs(m.root,approved)
    assert merge_sources(frozen,[])==frozen
    with pytest.raises(ValueError):m.select(pid,[{**refs[0],'sha256':'wrong'}])
    with pytest.raises(KeyError):m.select(s.create('Other','en')['id'],refs)
    path=m.root/'materials'/pid/a['id']/'parsed.json';path.write_text('[]')
    with pytest.raises(ValueError,match='integrity'):m.get(pid,a['id'])

def test_bounded_selection_and_file_count(materials):
    m,s,pid=materials;a=m.upload(pid,'big.txt','text/plain',('界'*(128*1024//3+1)).encode())
    with pytest.raises(ValueError,match='128 KiB'):m.select(pid,[{'id':a['id'],'sha256':a['sha256'],'locations':['L1']}])
    for _ in range(19):m.upload(pid,'x.txt','text/plain',b'x')
    with pytest.raises(ValueError,match='20'):m.upload(pid,'x.txt','text/plain',b'x')

def test_missing_private_original_has_actionable_path_free_error(materials):
    m,s,pid=materials;a=m.upload(pid,'x.txt','text/plain',b'x')
    (m.root/'materials'/pid/a['id']/'original').unlink()
    with pytest.raises(ValueError,match='unavailable.*Reimport'):m.get(pid,a['id'])

def test_parser_timeout_cleans_disposable_scope(materials,monkeypatch):
    m,s,pid=materials
    class Timeout:
        def __init__(self,*a):pass
        def probe(self):pass
        def run(self,args,**kwargs):raise subprocess.TimeoutExpired(args,20)
    monkeypatch.setattr('lab.materials.boundary_factory',Timeout)
    with pytest.raises(ValueError,match='time|limit'):m.upload(pid,'x.pdf','application/pdf',pdf())
    assert m.list(pid)==[] and not list((m.root/'material-tasks').glob('*'))

def test_upload_route_bounds_streaming_and_preserves_local_guards(tmp_path,monkeypatch):
    from lab.materials import Materials
    from lab.providers import Adapter
    def forbidden(*args,**kwargs):raise AssertionError('Uploading must never call a provider')
    monkeypatch.setattr(Adapter,'send',forbidden)
    monkeypatch.setenv('LAB_DATA_ROOT',str(tmp_path))
    monkeypatch.setattr(Materials,'parse',lambda self,raw,ext:[{'location':'L1','text':raw.decode()}])
    client=TestClient(create_app(db_path=tmp_path/'runs/lab.sqlite3'),base_url='http://127.0.0.1')
    p=client.post('/api/workspace/projects',headers=HEAD,json={'title':'Upload'}).json()
    url=f"/api/workspace/projects/{p['id']}/materials"
    headers={**HEAD,'Content-Type':'text/plain','X-Material-Name':'notes.txt'}
    assert client.post(url,headers=headers,content=b'x'*100001).status_code==200
    assert client.post(url,headers=headers,content=iter([b'x'*300000,b'x'*300000])).status_code==413
    assert client.post(url,headers=headers,content=b'x'*512001).status_code==413
    assert client.post(url,headers={**headers,'Content-Length':'not-a-number'},content=b'x').status_code==400
    assert client.post(url,headers={**headers,'Content-Length':'-1'},content=b'x').status_code==400
    assert client.post('/api/workspace/projects',headers=HEAD,content=iter([b'x'*60000,b'x'*60000])).status_code==413
    assert client.post(url,headers={**headers,'Origin':'http://evil.test'},content=b'x').status_code==403
    assert client.post(url,headers={'Content-Type':'text/plain'},content=b'x').status_code==403
    assert client.post('/api/workspace/projects/missing/materials',headers=headers,content=b'x').status_code==404
    assert client.get(url).json()[0]['name']=='notes.txt'
    assert not list((tmp_path/'runs').glob('workspace-receipts/*'))

def test_native_parser_real_readonly_boundary(tmp_path,monkeypatch):
    import os,shutil
    if os.name!='nt' or not shutil.which('codex'):pytest.skip('Windows MXC and Codex required')
    from lab.materials import Materials
    monkeypatch.setenv('LAB_EXECUTION_BACKEND','mxc')
    s=WorkspaceStore(tmp_path/'runs/state.sqlite3');p=s.create('Native parser','en');m=Materials(tmp_path,s)
    a=m.upload(p['id'],'notes.pdf','application/pdf',pdf())
    assert m.get(p['id'],a['id'])['units']==[{'location':'P1','text':'Buy after review'}]
    assert list((tmp_path/'material-tasks').iterdir())==[]

def test_native_parser_supports_bounded_unicode_preview(tmp_path,monkeypatch):
    import os,shutil
    if os.name!='nt' or not shutil.which('codex'):pytest.skip('Windows MXC and Codex required')
    from lab.materials import Materials
    monkeypatch.setenv('LAB_EXECUTION_BACKEND','mxc')
    s=WorkspaceStore(tmp_path/'runs/state.sqlite3');p=s.create('Unicode','en');m=Materials(tmp_path,s)
    raw=('文字😀'*20000).encode('utf-8')
    a=m.upload(p['id'],'notes.txt','text/plain',raw)
    assert m.get(p['id'],a['id'])['units'][0]['text']=='文字😀'*20000

@pytest.mark.parametrize('backend',['mxc','docker'])
@pytest.mark.parametrize('protected',['MATERIAL-REFERENCES.json','METHOD-VIEW.json','MATERIAL-INDEX.json','MATERIAL-001.txt'])
def test_construction_stages_and_protects_frozen_materials(materials,monkeypatch,backend,protected):
    from lab.build_runtime import Builder
    from lab.connections import Connections
    from lab.materials import reference_inputs
    import lab.build_runtime as runtime
    import lab.sdk_builder as sdk
    m,s,pid=materials;a=m.upload(pid,'numeric.md','text/markdown',b'ratio=0.125')
    frozen=m.select(pid,[{'id':a['id'],'sha256':a['sha256'],'locations':['L1']}])
    s.mutate(pid,lambda p:p.update(revision=1,draft={'scope':'x','rules':[{'topic':'ratio','rule':'use reference','source':'m1'}],'questions':[],'material_sources':frozen}))
    version=s.approve(pid,1)['versions'][0];s.mutate(pid,lambda p:p.update(busy=True,builds=[{'id':'b1','status':'running','events':[]}]))
    known_record={'id':'settled-fixture','status':'completed','committed_cost':0.002}
    s.mutate(pid,lambda p:p['records'].append(known_record))
    c=Connections(s);builder=Builder(s,c)
    expected=reference_inputs(version)
    cfg={'model':'offline','id':'offline','reasoning_effort':None}
    if backend=='mxc':
        class Relay:
            def __init__(self,*a):self.url='http://127.0.0.1:1';self.token='offline';self.rejection_error=None
            def __enter__(self):return self
            def __exit__(self,*a):pass
        monkeypatch.setattr(runtime,'BudgetRelay',Relay)
        def run(args,**kw):
            work=kw['cwd']
            if 'exec' in args:
                for name,text in expected.items():assert (work/name).read_text(encoding='utf-8')==text
                (work/protected).write_text('{}')
                return subprocess.CompletedProcess(args,0,'','')
            (work/'inside-probe.txt').write_text('ok')
            return subprocess.CompletedProcess(args,0,'ISOLATION_OK','')
        monkeypatch.setattr(runtime,'bounded_run',run)
    else:
        class Task:
            def __init__(self,*a,**kw):pass
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def seed(self,files):self.files=files;assert all(files[n]==text for n,text in expected.items())
            def probe(self):pass
            def inspect(self):pass
            def collect(self):return [{'name':n,'text':'{}' if n==protected else text} for n,text in self.files.items()]
        async def construct(*args):return 'offline fixture'
        monkeypatch.setattr(sdk,'DockerTask',Task);monkeypatch.setattr(sdk,'construct',construct)
    builder.run(pid,'b1',version,cfg,'never-sent',1,'docker' if backend=='docker' else 'codex')
    build=s.get(pid)['builds'][0]
    assert build['status']=='failed' and 'material' in build['error']
    assert s.get(pid)['records']==[known_record] and s.get(pid)['versions']==[version]

@pytest.mark.parametrize('valid',[True,False])
def test_clarification_grounding_and_revision_sources(materials,monkeypatch,valid):
    from lab.workspace_agent import WorkspaceAgent
    from lab.connections import Connections
    from lab.providers import Adapter
    from types import SimpleNamespace
    m,s,pid=materials;a=m.upload(pid,'helper.txt','text/plain',b'ratio=0.125')
    c=Connections(s);cfg=c.create({'provider':'openai','model':'offline','name':'offline','key':'never-sent','input_price':1,'output_price':1})
    monkeypatch.setenv('LAB_DATA_ROOT',str(m.root))
    def send(self,config,context,*args,**kw):
        data=json.loads(context['text']);assert data['material_sources'][0]['units'][0]['text']=='ratio=0.125'
        ref=f"material:{a['id']}:L1" if valid else 'material:invented:P99'
        citation={'id':a['id'],'sha256':a['sha256'],'start':'L1','end':'L1'}
        return SimpleNamespace(text=json.dumps({'message':'The ratio is 0.125. Is the date month-first?', 'scope':'daily','rules':[{'topic':'ratio','rule':'0.125','source':ref,'material_refs':[citation]}],'questions':[]}))
    monkeypatch.setattr(Adapter,'send',send)
    p=WorkspaceAgent(s,c).message(pid,{'text':'Use reference','connection_id':cfg['id'],'authorized':True,'budget':1,'material_refs':[{'id':a['id'],'sha256':a['sha256'],'locations':['L1']}]})
    assert p['records'][-1]['status']==('completed' if valid else 'failed')
    if valid:
        assert p['draft']['material_sources'][0]['sha256']==a['sha256']
        WorkspaceAgent(s,c).message(pid,{'text':'Retain ratio','connection_id':cfg['id'],'authorized':True,'budget':1})
        assert s.get(pid)['draft']['material_sources']==p['draft']['material_sources']

@pytest.fixture
def citation_project(materials,monkeypatch):
    from lab.workspace_agent import WorkspaceAgent
    from lab.connections import Connections
    m,s,pid=materials
    a=m.upload(pid,'method.txt','text/plain','\n'.join(f'原始规则 {i}' for i in range(1,41)).encode())
    c=Connections(s);cfg=c.create({'provider':'openai','model':'offline','name':'offline','key':'never-sent','input_price':1,'output_price':1})
    monkeypatch.setenv('LAB_DATA_ROOT',str(m.root))
    selected=[{'id':a['id'],'sha256':a['sha256'],'locations':[f'L{i}' for i in [*range(1,13),*range(23,36)]]}]
    def request(refs=selected):return WorkspaceAgent(s,c).message(pid,{'text':'保留原规则，不增加阈值。','connection_id':cfg['id'],'authorized':True,'budget':1,'material_refs':refs})
    return m,s,pid,a,request

@pytest.mark.parametrize('language',['zh-CN','en'])
def test_structured_material_attribution_preserves_multilingual_text_through_approval(citation_project,monkeypatch,language):
    from lab.providers import Adapter
    from lab.materials import reference_inputs
    from types import SimpleNamespace
    m,s,pid,a,request=citation_project
    prose=(f"材料：{a['id']}:L6-L9；{a['id']}:L5-L10、L23-L35；用户消息 m1" if language=='zh-CN' else f"Material notes {a['id']}:L6-L9; L5-L10 and L23-L35; user message m1")
    rule_text='退出缓冲为 0；比例 0.125。' if language=='zh-CN' else 'The exit buffer is 0; ratio is 0.125.'
    citations=[{'id':a['id'],'sha256':a['sha256'],'start':start,'end':end} for start,end in [('L6','L9'),('L5','L10'),('L23','L35')]]
    def send(self,config,context,*args,**kwargs):
        return SimpleNamespace(text=json.dumps({'message':'确认含义后再执行。','scope':'daily','rules':[{'topic':'Exit','rule':rule_text,'source':prose,'material_refs':citations}],'questions':[]}))
    monkeypatch.setattr(Adapter,'send',send)
    first=request()
    assert first['records'][-1]['status']=='completed'
    second=request([])
    assert second['records'][-1]['status']=='completed'
    assert second['draft']['rules'][0]=={'topic':'Exit','rule':rule_text,'source':prose,'material_refs':citations}
    approved=s.approve(pid,second['revision'])['versions'][-1]
    assert approved['method']['rules']==second['draft']['rules']
    staged=json.loads(reference_inputs(approved)['MATERIAL-REFERENCES.json'])
    assert staged['citations']==[{'rule_index':0,'material_refs':citations}]
    assert approved['method']['material_sources']==first['draft']['material_sources']

@pytest.mark.parametrize('invalid',['missing','empty','fabricated','cross-project','unselected','hash','location','gap','overflow','reverse','kind','display-id','display-overflow'])
def test_structured_material_reference_failure_cannot_create_approvable_draft(citation_project,monkeypatch,invalid):
    from lab.providers import Adapter
    from types import SimpleNamespace
    m,s,pid,a,request=citation_project
    citation={'id':a['id'],'sha256':a['sha256'],'start':'L6','end':'L9'}
    if invalid=='fabricated':citation['id']='f'*32
    if invalid=='cross-project':
        other=s.create('Other','en');foreign=m.upload(other['id'],'foreign.txt','text/plain',b'x')
        citation.update(id=foreign['id'],sha256=foreign['sha256'],start='L1',end='L1')
    if invalid=='unselected':
        other=m.upload(pid,'unselected.txt','text/plain',b'x');citation.update(id=other['id'],sha256=other['sha256'],start='L1',end='L1')
    if invalid=='hash':citation['sha256']='f'*64
    if invalid=='location':citation.update(start='L36',end='L36')
    if invalid=='gap':citation.update(start='L5',end='L24')
    if invalid=='overflow':citation.update(start='L1',end='L99999')
    if invalid=='reverse':citation.update(start='L9',end='L6')
    if invalid=='kind':citation.update(start='L6',end='P9')
    rule={'topic':'Exit','rule':'Keep ratio 0.125','source':f"材料：{a['id']}:L6-L9"}
    if invalid=='display-id':rule['source']='材料：'+'f'*32+':L6-L9'
    if invalid=='display-overflow':rule['source']=f"材料：{a['id']}:L6-L99999"
    if invalid!='missing':rule['material_refs']=[] if invalid=='empty' else [citation]
    monkeypatch.setattr(Adapter,'send',lambda *args,**kwargs:SimpleNamespace(text=json.dumps({'message':'Draft','scope':'daily','rules':[rule],'questions':[]})))
    failed=request()
    assert failed['records'][-1]['status']=='failed' and failed['draft'] is None and failed['revision']==0
    with pytest.raises(ValueError,match='No method draft'):s.approve(pid,0)

def test_invalid_revision_preserves_approved_method_and_prior_failed_record(citation_project,monkeypatch):
    from lab.providers import Adapter
    from types import SimpleNamespace
    m,s,pid,a,request=citation_project
    citation={'id':a['id'],'sha256':a['sha256'],'start':'L6','end':'L9'}
    rule={'topic':'Exit','rule':'Keep ratio 0.125','source':f"材料：{a['id']}:L6-L9",'material_refs':[citation]}
    payload={'message':'Draft','scope':'daily','rules':[rule],'questions':[]}
    monkeypatch.setattr(Adapter,'send',lambda *args,**kwargs:SimpleNamespace(text=json.dumps(payload)))
    good=request();approved=s.approve(pid,good['revision'])['versions'][0]
    rule['material_refs'][0]['end']='L99999'
    bad=request([]);saved_failure=bad['records'][-1]
    assert saved_failure['status']=='failed' and bad['draft']==good['draft'] and bad['versions']==[approved]
    rule['material_refs'][0]['end']='L9'
    good_again=request([])
    assert good_again['records'][-2]==saved_failure and good_again['versions']==[approved]

def test_material_citation_size_is_bounded_independently_of_source_text(citation_project,monkeypatch):
    from lab.providers import Adapter
    from types import SimpleNamespace
    m,s,pid,a,request=citation_project
    citation={'id':a['id'],'sha256':a['sha256'],'start':'L6','end':'L9'}
    rules=[{'topic':'Exit','rule':'Keep ratio 0.125','source':'From selected notes','material_refs':[citation]*10} for _ in range(50)]
    monkeypatch.setattr(Adapter,'send',lambda *args,**kwargs:SimpleNamespace(text=json.dumps({'message':'Draft','scope':'daily','rules':rules,'questions':[]})))
    result=request()
    assert result['records'][-1]['status']=='failed' and result['draft'] is None

def test_material_provider_schema_is_strict_and_approval_and_staging_recheck_citations(citation_project,monkeypatch):
    from lab.providers import Adapter
    from lab.materials import reference_inputs
    from types import SimpleNamespace
    m,s,pid,a,request=citation_project
    citation={'id':a['id'],'sha256':a['sha256'],'start':'L6','end':'L9'}
    def send(self,config,context,*args,**kwargs):
        schema=context['schema']
        for obj in [schema,*schema.get('$defs',{}).values()]:
            if obj.get('type')=='object':
                assert set(obj['required'])==set(obj['properties']) and obj['additionalProperties'] is False
        assert 'material_refs' in schema['$defs']['MaterialRule']['required']
        return SimpleNamespace(text=json.dumps({'message':'Draft','scope':'daily','rules':[{'topic':'Exit','rule':'Keep ratio 0.125','source':'用户消息 m1，与选定笔记','material_refs':[citation]}],'questions':[]}))
    monkeypatch.setattr(Adapter,'send',send)
    good=request();assert good['records'][-1]['status']=='completed'
    version=s.approve(pid,good['revision'])['versions'][0]
    bad=json.loads(json.dumps(version));bad['method']['rules'][0]['material_refs'][0]['end']='L13'
    with pytest.raises(ValueError,match='unselected'):reference_inputs(bad)
    def corrupt(p):p['draft']['rules'][0]['material_refs'][0]['sha256']='f'*64;p['revision']+=1
    s.mutate(pid,corrupt)
    with pytest.raises(ValueError,match='hash'):s.approve(pid,good['revision']+1)
    assert s.get(pid)['versions']==[version]

def test_provider_constrains_citation_identities_to_this_requests_selected_sources(citation_project,monkeypatch):
    from lab.providers import Adapter
    from lab.workspace_agent import MaterialReply
    from types import SimpleNamespace
    m,s,pid,a,request=citation_project
    other=m.upload(pid,'unselected.txt','text/plain',b'Not selected')
    captured=[]
    citation={'id':a['id'],'sha256':a['sha256'],'start':'L6','end':'L9'}
    def send(self,config,context,*args,**kwargs):
        _,wire=self.build(config,context,[],allow_tools=False)
        captured.append(wire['text']['format']['schema']['$defs']['MaterialCitation']['properties'])
        return SimpleNamespace(text=json.dumps({'message':'Draft','scope':'daily',
            'rules':[{'topic':'Exit','rule':'Keep ratio 0.125','source':'Selected notes','material_refs':[citation]}],'questions':[]}))
    monkeypatch.setattr(Adapter,'send',send)
    first=request();second=request([])
    assert first['records'][-1]['status']=='completed' and second['records'][-1]['status']=='completed'
    for props in captured:
        assert props['id'].get('enum')==[a['id']]
        assert props['sha256'].get('enum')==[a['sha256']]
        assert other['id'] not in props['id']['enum']
    assert 'enum' not in MaterialReply.model_json_schema()['$defs']['MaterialCitation']['properties']['sha256']
