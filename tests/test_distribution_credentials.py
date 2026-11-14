import json
import pytest
from lab.connections import Connections
from lab.workspace_store import WorkspaceStore


def connection(tmp_path):
    store=WorkspaceStore(tmp_path/'workspace.sqlite3'); connections=Connections(store)
    cfg=connections.create(dict(provider='openai',model='model',name='test',key='old-key-123',input_price=1,output_price=2))
    return store,connections,cfg


def test_renew_preserves_identity_roles_and_history_but_invalidates_old_generation(tmp_path):
    store,c,cfg=connection(tmp_path);p=store.create('P','en')
    c.assign_roles(p['id'],dict(builder=cfg['id'],execution=None))
    c.verified(cfg['id']);c.construction_observed(cfg['id'])
    before,key=c.get(cfg['id'])
    renewed=c.renew(cfg['id'],dict(key='new-key-456'))
    assert renewed['id']==cfg['id'] and renewed['model']=='model' and renewed['input_price']==1
    assert renewed['generation']==2 and renewed['verification']=='not_tested'
    assert 'construction' not in renewed and 'new-key' not in json.dumps(renewed)
    assert c.get(cfg['id'])[1]=='new-key-456'
    assert store.get(p['id'])['model_roles']['builder']==cfg['id']
    with pytest.raises(ValueError,match='renewed'):c.assert_generation(before)


def test_renew_rejects_active_connection_without_changing_key(tmp_path):
    store,c,cfg=connection(tmp_path);p=store.create('P','en')
    c.assign_roles(p['id'],dict(builder=cfg['id'],execution=None))
    store.mutate(p['id'],lambda p:p.update(busy=True))
    with pytest.raises(ValueError,match='active'):c.renew(cfg['id'],dict(key='new-key-456'))
    assert c.get(cfg['id'])[1]=='old-key-123'


def test_inaccessible_protected_key_is_unconfigured_and_repairable(tmp_path,monkeypatch):
    store,c,cfg=connection(tmp_path)
    with store.connect() as db:db.execute('UPDATE connections SET secret=? WHERE id=?',('inaccessible',cfg['id']))
    c.session.clear()
    def unavailable(*args):raise RuntimeError('no DPAPI')
    monkeypatch.setattr('lab.connections.protect',unavailable)
    assert c.list()[0]['configured'] is False
    with pytest.raises(ValueError,match='Re-enter'):c.get(cfg['id'])
    c.renew(cfg['id'],dict(key='new-key-456'))
    assert c.list()[0]['configured'] is True


def test_conversation_preparation_rejects_rekey_race(tmp_path,monkeypatch):
    from lab.workspace_agent import WorkspaceAgent
    from lab.providers import Adapter
    store,c,cfg=connection(tmp_path);p=store.create('P','en')
    original=Adapter.build
    def raced(self,*args,**kwargs):
        result=original(self,*args,**kwargs)
        c.renew(cfg['id'],{'key':'replacement-key'})
        return result
    monkeypatch.setattr(Adapter,'build',raced)
    with pytest.raises(ValueError,match='renewed'):
        WorkspaceAgent(store,c).message(p['id'],dict(text='My method',authorized=True,budget=1,connection_id=cfg['id']))
    assert store.get(p['id'])['records']==[] and not store.get(p['id'])['busy']


def test_late_observation_cannot_verify_replacement_key(tmp_path):
    store,c,cfg=connection(tmp_path)
    c.renew(cfg['id'],dict(key='new-key-123'))
    c.verified(cfg['id'],generation=1)
    c.construction_observed(cfg['id'],generation=1)
    current,_=c.get(cfg['id'])
    assert current['verification']=='not_tested' and 'construction' not in current


def test_persistence_capability_fails_closed_when_os_protection_unavailable(monkeypatch):
    def unavailable(*args):raise ValueError('OS protection unavailable')
    monkeypatch.setattr('lab.connections.protect',unavailable)
    assert Connections.capability()['persistent'] is False


def test_catalog_capture_dispatch_race_never_sends_renewed_key(tmp_path,monkeypatch):
    import threading
    store,c,cfg=connection(tmp_path);captured=threading.Event();resume=threading.Event();sent=[];errors=[]
    original=c.get
    def paused(cid):
        result=original(cid)
        if not captured.is_set():
            captured.set();assert resume.wait(2)
        return result
    monkeypatch.setattr(c,'get',paused)
    monkeypatch.setattr(c,'_catalog',lambda provider,key:sent.append(key) or {'models':['model']})
    def check():
        try:c.check(cfg['id'])
        except ValueError as exc:errors.append(str(exc))
    thread=threading.Thread(target=check)
    try:
        thread.start();assert captured.wait(2)
        assert c.renew(cfg['id'],{'key':'new-key-456'})['generation']==2
    finally:resume.set();thread.join(2)
    assert not thread.is_alive() and sent==[]
    assert len(errors)==1 and 'renewed' in errors[0]


@pytest.mark.parametrize('fails',[False,True])
def test_active_catalog_claim_blocks_renewal_and_releases_finally(tmp_path,monkeypatch,fails):
    import threading
    store,c,cfg=connection(tmp_path);dispatched=threading.Event();resume=threading.Event();errors=[]
    def catalog(provider,key):
        assert key=='old-key-123';dispatched.set();assert resume.wait(2)
        if fails:raise ValueError('catalog fixture unavailable')
        return {'models':['model']}
    monkeypatch.setattr(c,'_catalog',catalog)
    def check():
        try:c.check(cfg['id'])
        except ValueError as exc:errors.append(str(exc))
    thread=threading.Thread(target=check)
    try:
        thread.start();assert dispatched.wait(2)
        with pytest.raises(ValueError,match='active'):c.renew(cfg['id'],{'key':'new-key-456'})
        assert c.get(cfg['id'])[1]=='old-key-123'
    finally:resume.set();thread.join(2)
    assert not thread.is_alive()
    assert errors==(['catalog fixture unavailable'] if fails else [])
    assert c.renew(cfg['id'],{'key':'new-key-456'})['generation']==2
