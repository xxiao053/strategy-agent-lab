"""Bounded machine attribution, independent of the conversation's language."""
import re
import json
import unicodedata

_UNIT=re.compile(r'([LPRI])([1-9][0-9]{0,4})\Z')
_PART=r'[A-Za-z][0-9]+(?:\s*-\s*[A-Za-z]?[0-9]+)?'
_DISPLAY=re.compile(r'(?:(?:material|材料)\s*:\s*([A-Za-z0-9_-]+)|([a-fA-F0-9]{32}))\s*:\s*('+_PART+r'(?:\s*[,、]\s*'+_PART+r')*)',re.I)


def _range(start,end):
    first=_UNIT.fullmatch(start);last=_UNIT.fullmatch(end)
    if not first or not last or first[1]!=last[1]:raise ValueError('Invalid material citation location.')
    lo,hi=int(first[2]),int(last[2])
    if not lo<=hi or hi-lo>=1000:raise ValueError('Material citation range exceeds its bound.')
    return {f'{first[1]}{index}' for index in range(lo,hi+1)}


def _display_references(source):
    # Supporting consistency check, never the authoritative source contract.
    text=unicodedata.normalize('NFKC',source).translate(str.maketrans({'–':'-','—':'-','‑':'-','‐':'-'}))
    for match in _DISPLAY.finditer(text):
        for part in re.split(r'\s*[,、]\s*',match[3]):
            endpoints=re.split(r'\s*-\s*',part)
            start=endpoints[0];end=endpoints[-1]
            if end[0].isdigit():end=start[0]+end
            yield match[1] or match[2],_range(start,end)


def validate_material_citations(rules,sources):
    """Validate every unit and hash against only the supplied frozen source set.

    Legacy methods without structured material attribution remain readable;
    material-aware replies must call this before saving a new method draft.
    """
    allowed={item['id']:(item['sha256'],{unit['location'] for unit in item['units']}) for item in sources}
    records=[]
    for index,rule in enumerate(rules):
        refs=rule.get('material_refs',[])
        if not isinstance(refs,list) or len(refs)>10:raise ValueError('Invalid structured material citations.')
        cited={}
        for ref in refs:
            if not isinstance(ref,dict) or set(ref)!={'id','sha256','start','end'} or any(not isinstance(value,str) for value in ref.values()):
                raise ValueError('Invalid structured material citation.')
            if ref['id'] not in allowed or ref['sha256']!=allowed[ref['id']][0]:
                raise ValueError('Material citation identity or hash is not in the selected sources.')
            locations=_range(ref['start'],ref['end'])
            if not locations<=allowed[ref['id']][1]:raise ValueError('Material citation includes an unselected location.')
            cited.setdefault(ref['id'],set()).update(locations)
        for mid,locations in _display_references(rule['source']):
            if mid not in cited or not locations<=cited[mid]:
                raise ValueError('Readable material citation conflicts with structured attribution.')
        if refs:records.append({'rule_index':index,'material_refs':refs})
    if sources and rules and not records:raise ValueError('Material-aware rules need structured material attribution.')
    if len(json.dumps(records,ensure_ascii=False).encode('utf-8'))>24000:
        raise ValueError('Structured material attribution exceeds 24,000 bytes.')
    return records
