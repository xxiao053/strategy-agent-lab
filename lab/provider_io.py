"""Bound provider bodies before JSON/SSE parsing; no decompression of remote input."""
import time


def validate_headers(response,limit):
    if response.headers.get('content-encoding','identity').strip().lower()!='identity':
        raise ValueError('Unsupported provider content encoding.')
    length=response.headers.get('content-length')
    if length is not None and (not length.isdecimal() or int(length)>limit):
        raise ValueError('Provider response exceeds the capture limit.')


def chunks(response,*,limit,deadline):
    validate_headers(response,limit)
    total=0
    # Do not aggregate into a requested chunk size: observe trickled bytes too.
    # The HTTP client's idle timeout independently bounds a stalled socket read.
    for chunk in response.iter_bytes():
        if time.monotonic()>deadline:raise ValueError('Provider response deadline exceeded.')
        total+=len(chunk)
        if total>limit:raise ValueError('Provider response exceeds the capture limit.')
        yield chunk
    if time.monotonic()>deadline:raise ValueError('Provider response deadline exceeded.')


def lines(response,*,limit,line_limit,deadline):
    pending=bytearray();skip_lf=False
    for chunk in chunks(response,limit=limit,deadline=deadline):
        if skip_lf and chunk:
            if chunk.startswith(b'\n'):chunk=chunk[1:]
            skip_lf=False
        pending.extend(chunk)
        while True:
            endings=[i for i in (pending.find(b'\n'),pending.find(b'\r')) if i>=0]
            if not endings:break
            split=min(endings)
            if split>line_limit:raise ValueError('Provider stream line exceeds the capture limit.')
            line=bytes(pending[:split]).decode('utf-8');carriage=pending[split]==13
            del pending[:split+1]
            if carriage:
                if pending.startswith(b'\n'):del pending[:1]
                elif not pending:skip_lf=True
            yield line
        if len(pending)>line_limit:raise ValueError('Provider stream line exceeds the capture limit.')
    if pending:yield bytes(pending).decode('utf-8')
