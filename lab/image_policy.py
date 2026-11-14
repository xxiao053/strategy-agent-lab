"""Shared trusted image limits and deliberately conservative token reservations.

token-v1 is operator-confirmed token billing, not universal provider billing math.
Per-image fees, custom endpoints and other billing profiles are unsupported.
"""
import base64
import hashlib
import struct
import zlib
from pathlib import Path
from .billing import reserve_cost,RESERVATION_MULTIPLIER

RAW_LIMIT=2000000
PIXEL_LIMIT=16000000
OUTPUT_LIMIT=512000
EDGE_LIMIT=1024
NORMALIZATION='rgb-png-v1'
POLICY='image-token-v1'
TOKEN_ADAPTERS={'openai','anthropic','gemini'}
RATE_MULTIPLIERS={'input':RESERVATION_MULTIPLIER,'output':RESERVATION_MULTIPLIER}
MIN_IMAGE_TOKENS=32768


def cost_estimate(cfg,input_tokens,output_tokens):
    return reserve_cost(cfg,input_tokens,output_tokens)


def require_connection(cfg):
    if cfg.get('image_inputs') is not True:
        raise ValueError('Images retained. Choose or enable image inputs on the selected model connection; no request sent.')
    if cfg.get('provider') not in TOKEN_ADAPTERS or cfg.get('image_billing_profile')!='token-v1':
        raise ValueError('Unsupported image billing profile or adapter. Use a supported token-billed image connection; no request sent.')


def inspect_png(raw,meta):
    """Check a boundary-produced identity/header only; never decode hostile images on host."""
    if not 0<len(raw)<=OUTPUT_LIMIT or raw[:16]!=b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' or len(raw)<33:
        raise ValueError('Invalid normalized image; reimport a supported still image.')
    width,height=struct.unpack('>II',raw[16:24])
    if not 1<=width<=EDGE_LIMIT or not 1<=height<=EDGE_LIMIT or raw[24:26]!=bytes([8,2]):
        raise ValueError('Invalid normalized RGB image dimensions.')
    if (meta.get('sha256')!=hashlib.sha256(raw).hexdigest() or meta.get('width')!=width or meta.get('height')!=height
        or meta.get('bytes')!=len(raw) or meta.get('normalization')!=NORMALIZATION):
        raise ValueError('Image identity changed; reimport the image.')
    offset=8;seen=[]
    while offset<len(raw):
        if offset+12>len(raw):raise ValueError('Invalid normalized PNG structure.')
        size=struct.unpack('>I',raw[offset:offset+4])[0];kind=raw[offset+4:offset+8];end=offset+12+size
        if end>len(raw) or kind not in {b'IHDR',b'IDAT',b'IEND'}:raise ValueError('Invalid normalized PNG chunks.')
        if struct.unpack('>I',raw[end-4:end])[0]!=zlib.crc32(raw[offset+4:end-4]):raise ValueError('Invalid normalized PNG checksum.')
        seen.append(kind);offset=end
    if not seen or seen[0]!=b'IHDR' or seen[-1]!=b'IEND' or seen.count(b'IHDR')!=1 or seen.count(b'IEND')!=1 or b'IDAT' not in seen:
        raise ValueError('Invalid normalized PNG order.')
    return raw


def private_directory(root,path):
    """Create controller-selected private directories without following existing links."""
    root,path=Path(root).absolute(),Path(path).absolute()
    try:
        relative=path.relative_to(root);root.mkdir(parents=True,exist_ok=True)
        current=root
        for part in ('',*relative.parts):
            if part:current=current/part
            if current.exists() or current.is_symlink():
                stat=current.lstat()
                if not current.is_dir() or current.is_symlink() or getattr(stat,'st_file_attributes',0)&0x400:raise OSError()
            else:current.mkdir()
        return path
    except (OSError,ValueError):raise ValueError('Private image directory unavailable or unsafe; no file was written.') from None


def private_read(root,path,limit):
    root,path=Path(root).resolve(),Path(path)
    try:
        relative=path.absolute().relative_to(root)
        current=root
        for part in relative.parts:
            current=current/part;stat=current.lstat()
            if current.is_symlink() or getattr(stat,'st_file_attributes',0)&0x400:raise OSError()
        if not path.is_file() or path.stat().st_size>limit:raise OSError()
        with path.open('rb') as stream:raw=stream.read(limit+1)
        if len(raw)>limit:raise OSError()
        return raw
    except (OSError,ValueError):raise ValueError('Private image unavailable or changed. Reimport or create a new run.') from None


def preflight(cfg,images,wire_bytes,output_tokens,*,text_bytes,max_images=2,max_wire_bytes=1600000):
    require_connection(cfg)
    if not 1<=len(images)<=max_images:raise ValueError(f'An active method context supports at most {max_images} images; remove a selection or start a narrower method.')
    if wire_bytes>max_wire_bytes:raise ValueError(f'Image request exceeds {max_wire_bytes:,} wire bytes; reduce selected context.')
    tokens=0;identities=[]
    for image in images:
        data=image.get('data','')
        if not isinstance(data,str) or len(data)>4*((OUTPUT_LIMIT+2)//3):raise ValueError('Invalid image payload size.')
        try:raw=base64.b64decode(data,validate=True)
        except ValueError:raise ValueError('Invalid normalized image payload.') from None
        inspect_png(raw,image)
        tokens+=max(MIN_IMAGE_TOKENS,len(data),image['width']*image['height'])
        identities.append({k:image[k] for k in ('sha256','width','height','bytes','normalization')})
    reserve=cost_estimate(cfg,text_bytes+8000+tokens,output_tokens)
    return dict(policy=POLICY,configured=True,billing_profile='token-v1',rate_multipliers=dict(RATE_MULTIPLIERS),minimum_image_input_tokens=MIN_IMAGE_TOKENS,count=len(images),images=identities),reserve


def usage_accounted(provider,raw):
    usage=raw.get('usageMetadata' if provider=='gemini' else 'usage') or {}
    keys=('promptTokenCount','candidatesTokenCount') if provider=='gemini' else ('input_tokens','output_tokens')
    return all(type(usage.get(k)) is int and usage[k]>=0 for k in keys) and usage[keys[0]]>0
