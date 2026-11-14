"""Trusted parser entrypoint copied into a networkless, read-only task scope."""
import base64
import csv
import io
import json
import sys
from pathlib import Path


def parse_image(raw,extension):
    from PIL import Image,ImageOps
    import hashlib
    import warnings
    if not 0<len(raw)<=2000000:raise ValueError('Image exceeds 2,000,000 bytes. Export a smaller PNG or JPEG.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as validation:validation.verify()
            with Image.open(io.BytesIO(raw)) as source:
                if source.format!=('PNG' if extension=='.png' else 'JPEG'):
                    raise ValueError('Image type does not match its extension.')
                if source.width*source.height>16000000:raise ValueError('Image exceeds 16,000,000 pixels. Resize before importing.')
                if getattr(source,'n_frames',1)!=1:raise ValueError('Image must contain one still frame; export a static PNG or JPEG.')
                original_size=source.size
                source.load()
                oriented=ImageOps.exif_transpose(source)
                oriented.thumbnail((1024,1024),Image.Resampling.LANCZOS)
                oriented=oriented.convert('RGBA')
                background=Image.new('RGBA',oriented.size,'white');background.alpha_composite(oriented)
                image=background.convert('RGB')
                # Preserve readable detail: reject noisy images instead of silently shrinking/cropping further.
                clean=Image.new('RGB',image.size);clean.paste(image)
                out=io.BytesIO();clean.save(out,format='PNG',optimize=True)
                data=out.getvalue()
                if len(data)>512000:raise ValueError('Image normalization exceeds 512,000 bytes. Export a smaller or simpler image; no crop was applied.')
                meta=dict(sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),width=clean.width,height=clean.height,
                          original_width=original_size[0],original_height=original_size[1],normalization='rgb-png-v1',
                          orientation_applied=True,alpha_background='white',metadata_removed=True)
                return dict(units=[dict(location='I1',text='Visual source I1. No OCR or quotations extracted. Coding uses only the approved visual interpretation and rules.')],
                            image=meta,data=base64.b64encode(data).decode())
    except ValueError:raise
    except Exception:raise ValueError('Image could not be decoded safely. Export a valid still PNG or JPEG.') from None


def parse(raw,extension):
    units=[]
    if extension=='.pdf':
        from pypdf import PdfReader
        if not raw.startswith(b'%PDF-'):raise ValueError('Invalid PDF. Export a text-extractable PDF and try again.')
        reader=PdfReader(io.BytesIO(raw),strict=True)
        if reader.is_encrypted:raise ValueError('This PDF is encrypted. Upload an unencrypted copy.')
        if len(reader.pages)>100:raise ValueError('PDF exceeds 100 pages. Split the document.')
        for index,page in enumerate(reader.pages,1):
            # pypdf extraction can expand compressed streams; OS memory/time bounds remain essential.
            units.append({'location':f'P{index}','text':page.extract_text() or ''})
        if not any(u['text'].strip() for u in units):
            raise ValueError('No text could be extracted. Scanned/image-only PDF OCR is not supported.')
    else:
        try:text=raw.decode('utf-8-sig')
        except UnicodeDecodeError:raise ValueError('Use UTF-8 text or CSV encoding.') from None
        if '\x00' in text:raise ValueError('Binary content is not supported. Use UTF-8 text.')
        if extension=='.csv':
            csv.field_size_limit(100000)
            headers=[]
            for index,row in enumerate(csv.reader(io.StringIO(text,newline=''),strict=True),1):
                if index>1000:raise ValueError('CSV exceeds 1,000 rows. Split the file.')
                if len(row)>50:raise ValueError('CSV exceeds 50 columns.')
                if index==1:headers=row
                units.append({'location':f'R{index}','text':' | '.join(f'C{column} [{headers[column-1] if column<=len(headers) else ""}]: {value}' for column,value in enumerate(row,1))})
        else:
            units=[{'location':f'L{i}','text':line} for i,line in enumerate(text.splitlines(),1)]
            if len(units)>10000:raise ValueError('Text exceeds 10,000 lines. Split the file.')
    if sum(len(u['text']) for u in units)>100000:raise ValueError('Extracted text exceeds 100,000 characters. Split the file.')
    if not units or not any(u['text'].strip() for u in units):raise ValueError('No readable text found.')
    return units


if __name__=='__main__':
    try:
        payload=json.loads(Path('input.json').read_text(encoding='utf-8'))
        raw=(b''.join(Path(f'image-{i}.bin').read_bytes() for i in range(payload['image_chunks']))
             if payload['extension'] in {'.png','.jpg','.jpeg'} and type(payload.get('image_chunks')) is int and 1<=payload['image_chunks']<=2
             else base64.b64decode(payload['data'],validate=True))
        result=parse_image(raw,payload['extension']) if payload['extension'] in {'.png','.jpg','.jpeg'} else {'units':parse(raw,payload['extension'])}
    except ValueError as exc:
        # Only our bounded actionable messages leave the boundary, not parser traces.
        safe=('Image ','Invalid PDF.','This PDF is encrypted.','PDF exceeds','No text could','Use UTF-8','Binary content','CSV exceeds','Text exceeds','Extracted text exceeds','No readable text')
        result={'error':str(exc) if str(exc).startswith(safe) else 'Material could not be parsed. Check the file format or export a new copy.'}
    except Exception:
        result={'error':'Material could not be parsed. Check the file format or export a new copy.'}
    sys.stdout.buffer.write(json.dumps(result,ensure_ascii=False).encode('utf-8'))
