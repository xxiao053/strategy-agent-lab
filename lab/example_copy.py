"""Create unapproved local drafts from fixed, shipped example records."""
import copy
import hashlib
import json
import re
import uuid
from pathlib import Path

from .docker_policy import safe_name
from .image_policy import private_read
from .material_citations import validate_material_citations
from .materials import construction_inputs, merge_sources
from .workspace_agent import MaterialReply
from .workspace_store import now

EXAMPLES = {'cup-complete', 'nvda-revision'}


def excerpt_bytes(units):
    return json.dumps(units, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _files(files):
    if not isinstance(files, list) or len(files) > 80:
        raise ValueError('Invalid example source files.')
    seen = set(); total = 0; result = []
    for item in files:
        if not isinstance(item, dict): raise ValueError('Invalid example source file.')
        name = item.get('name'); text = item.get('text')
        if not isinstance(name, str): raise ValueError('Invalid example source filename.')
        safe_name(name)
        folded = name.casefold()
        if any(folded == old or folded.startswith(old+'/') or old.startswith(folded+'/') for old in seen):
            raise ValueError('Invalid example source filename.')
        if not isinstance(text, str): raise ValueError('Invalid example source text.')
        raw = text.encode('utf-8'); total += len(raw); seen.add(folded)
        if len(raw)>256000 or total>1000000 or hashlib.sha256(raw).hexdigest()!=item.get('sha256'):
            raise ValueError('Example source integrity or size check failed.')
        if name.endswith('.py') or name in {'execution.json','README.md'}:
            result.append({'name':name, 'text':text, 'sha256':item['sha256']})
    return result


def starter_artifacts(project):
    """Untrusted editing inputs only; never carry a previous validation/seal."""
    return _files(project.get('starter_files', []))


class ExampleCopies:
    def __init__(self, root, store):
        self.root = Path(root); self.store = store

    def create(self, example_id, body):
        if example_id not in EXAMPLES: raise KeyError(example_id)
        if not isinstance(body,dict) or set(body)-{'title','locale','version'}:
            raise ValueError('Choose an example version, project name and language only.')
        locale = body.get('locale','en')
        if not isinstance(locale,str) or locale not in {'en','zh-CN'}: raise ValueError('Choose a supported language.')
        try:
            raw = private_read(self.root,self.root/'examples/builder'/example_id/'project.json',4*1024*1024)
            package = json.loads(raw)
        except (OSError, ValueError):
            raise ValueError('The included example is unavailable or changed.') from None
        if package.get('schema')!='saved-builder-example-v1' or package.get('id')!=example_id:
            raise ValueError('Invalid included example.')
        title = body.get('title', package['title'] + (' · 副本' if locale=='zh-CN' else ' · copy'))
        if not isinstance(title,str) or not 1<=len(title.strip())<=100:
            raise ValueError('Enter a project name up to 100 characters.')
        number = body.get('version',package['versions'][-1]['number'])
        if type(number) is not int: raise ValueError('Choose an included method version.')
        version = next((v for v in package['versions'] if v['number']==number),None)
        build = next((b for b in reversed(package['builds']) if b['version']==number),None)
        if not version or not build: raise ValueError('Choose an included method and implementation.')
        files = _files(build['files'])
        materials = package['materials']
        if not isinstance(materials,list) or len(materials)>20:
            raise ValueError('Invalid included materials.')
        mapping = {}; sources = []; metas = []
        for material in materials:
            old = material['id']; units = material['units']
            if old in mapping or not isinstance(units,list) or not 1<=len(units)<=1000:
                raise ValueError('Invalid included material locations.')
            locations = set()
            for unit in units:
                if (set(unit)!={'location','text'} or not isinstance(unit['text'],str) or
                        not re.fullmatch(r'[LPRI][1-9][0-9]{0,4}',unit['location']) or unit['location'] in locations):
                    raise ValueError('Invalid included material location.')
                locations.add(unit['location'])
            data = excerpt_bytes(units)
            if len(data)>128*1024: raise ValueError('Included material exceeds context limits.')
            mid = uuid.uuid4().hex; sha = hashlib.sha256(data).hexdigest()
            mapping[old] = (mid,sha)
            sources.append(dict(id=mid,sha256=sha,name=material['name'],units=copy.deepcopy(units)))
            metas.append(dict(id=mid,sha256=sha,parsed_sha256=sha,name=material['name'],format='excerpt',
                bytes=len(data),locations=len(units),created=now(),source_kind='example_excerpt'))
        rules = copy.deepcopy(version['rules'])
        for rule in rules:
            for ref in rule.get('material_refs',[]):
                source = next((m for m in materials if m['id']==ref['id']),None)
                if not source or source['sha256']!=ref['sha256']:
                    raise ValueError('Included material citation does not match its source.')
                ref['id'],ref['sha256'] = mapping[ref['id']]
            for old,(mid,_) in mapping.items():
                rule['source'] = rule['source'].replace(old,mid)
            rule.setdefault('material_refs',[])
        method = MaterialReply(message='Copy',scope=version['scope'],rules=rules,questions=[]).model_dump(exclude={'message'})
        method['material_sources'] = merge_sources([],sources)
        validate_material_citations(method['rules'],method['material_sources'])
        construction_inputs({'method':method},'contract')
        initial = dict(revision=1,draft=method,materials=metas,example_sources=sources,starter_files=files,
            example_origin=dict(id=example_id,version=number,title=package['title'],package_sha256=hashlib.sha256(raw).hexdigest()))
        return self.store.create(title.strip(),locale,initial=initial)
