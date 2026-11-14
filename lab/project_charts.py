"""Trusted generic OHLCV charts, from visible history only; no generated image input."""
import base64
import hashlib
import io
import re
from PIL import Image,ImageDraw,ImageFont
from .contracts import Bar,iso
from .execution_contract import digest
from .image_policy import NORMALIZATION,OUTPUT_LIMIT,inspect_png,private_read,private_directory

CHART_EVIDENCE_FIELDS=('sha256','bytes','width','height','normalization','source')


def chart_source(context,symbol,*,history_bars=120,candidate=None):
    if not isinstance(symbol,str) or not re.fullmatch(r'[A-Z][A-Z0-9.-]{0,9}',symbol):raise ValueError('Invalid chart symbol.')
    cutoff=iso(context['cutoff']);raw=context.get('bars',{}).get(symbol)
    if not isinstance(raw,list) or not 1<=len(raw)<=501:raise ValueError('Chart symbol requires 1–501 visible bars.')
    bars=[Bar.model_validate(b) for b in raw]
    dates=[b.date for b in bars]
    if dates!=sorted(set(dates)) or dates[-1]!=cutoff or any(d>cutoff for d in dates):raise ValueError('Chart dates are outside ordered cutoff-limited history.')
    if type(history_bars) is not int or not 1<=history_bars<=501:raise ValueError('Invalid chart history.')
    bars=bars[-history_bars:];dates=[b.date for b in bars]
    data=[b.model_dump() for b in bars]
    source=dict(symbol=symbol,cutoff=cutoff,start=dates[0],end=dates[-1],dates=dates,bar_count=len(bars),visible_bar_count=len(raw),
                omitted_earlier_bars=len(raw)-len(bars),data_sha256=digest(data),renderer='ohlcv-v1',
                bounds='Latest at most 120 visible daily bars; linear raw OHLC price and volume. No future bars, annotations, benchmark or uploaded examples.')
    if history_bars!=120 or candidate is not None:
        source.update(renderer='ohlcv-v2',history_bars=history_bars,
                      bounds='Declared visible daily history; linear raw OHLC price and volume. Fixed dated candidate markers only; no future or uploaded example data.')
        if candidate is not None:
            markers=candidate.get('dates',{})
            if not markers or len(markers)>20 or any(day not in dates for day in markers.values()):raise ValueError('Candidate marker outside visible chart dates.')
            source['candidate']=dict(candidate_id=candidate['candidate_id'],dates=dict(markers))
    return bars,source


def render_chart(context,symbol,*,history_bars=120,candidate=None):
    bars,source=chart_source(context,symbol,history_bars=history_bars,candidate=candidate);dates=source['dates'];cutoff=source['cutoff']
    im=Image.new('RGB',(1024,640),'white');draw=ImageDraw.Draw(im);font=ImageFont.load_default(size=14)
    draw.text((72,12),f'{symbol} | As of {cutoff} | {dates[0]} to {dates[-1]}',font=font,fill='black')
    draw.text((72,35),f'Raw OHLC / linear USD | {len(bars)} of {source["visible_bar_count"]} visible bars | volume in shares',font=font,fill='black')
    left,right,top,bottom=80,1000,75,440
    low=min(b.low for b in bars);high=max(b.high for b in bars);pad=max((high-low)*.05,.01);low-=pad;high+=pad
    maxvol=max(max(b.volume for b in bars),1)
    y=lambda value:bottom-(value-low)/(high-low)*(bottom-top)
    x=lambda index:left+(index+.5)*(right-left)/len(bars)
    for i in range(6):
        value=low+(high-low)*i/5;at=y(value)
        draw.line((left,at,right,at),fill='#dddddd');draw.text((4,at-7),f'{value:.2f}',font=font,fill='black')
    width=max(1,min(8,(right-left)/len(bars)*.3))
    for i,b in enumerate(bars):
        color='#00806a' if b.close>=b.open else '#ce5a50';at=x(i)
        draw.line((at,y(b.high),at,y(b.low)),fill=color,width=1)
        draw.rectangle((at-width,min(y(b.open),y(b.close)),at+width,max(y(b.open),y(b.close))+1),fill=color)
        draw.rectangle((at-width,565-b.volume/maxvol*85,at+width,565),fill=color)
    draw.text((4,470),f'{maxvol:g}',font=font,fill='black');draw.text((4,550),'0',font=font,fill='black')
    for i in sorted({round(j*(len(bars)-1)/4) for j in range(5)}):
        draw.text((min(max(x(i)-38,left-10),right-80),580),dates[i],font=font,fill='black')
    if candidate:
        for index,(label,day) in enumerate(candidate['dates'].items()):
            at=x(dates.index(day));draw.line((at,top,at,bottom),fill='#8899bb',width=1)
            draw.text((min(at+2,right-150),top+(index%3)*16),label[:20],font=font,fill='#304a72')
        draw.text((72,612),f"Fixed candidate: {candidate['candidate_id']} | {len(bars)} visible bars",font=font,fill='black')
    else:draw.text((72,612),f'Latest <={history_bars} visible bars; no pattern markers. Earlier bars may be omitted.',font=font,fill='black')
    out=io.BytesIO();im.save(out,format='PNG',optimize=True);png=out.getvalue()
    image=dict(sha256=hashlib.sha256(png).hexdigest(),bytes=len(png),width=1024,height=640,normalization=NORMALIZATION,source=source)
    inspect_png(png,image)
    return dict(image,data=base64.b64encode(png).decode())


def save_chart(store,pid,rid,image):
    # IDs are controller-owned; chart digests are the only filename component.
    if any(not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',v) for v in (pid,rid)):raise ValueError('Invalid image storage identity.')
    folder=store.path.parent/'project-run-images'/pid/rid
    private_directory(store.path.parent,folder)
    files=list(folder.iterdir())
    target=folder/(image['sha256']+'.png')
    if not target.exists() and (len(files)>=1000 or sum(f.lstat().st_size for f in files)+image['bytes']>512*1024*1024):
        raise ValueError('Run chart storage limit reached (1000 images / 512 MiB).')
    png=inspect_png(base64.b64decode(image['data'],validate=True),image)
    try:
        with target.open('xb') as stream:stream.write(png)
    except FileExistsError:
        if private_read(store.path.parent,target,OUTPUT_LIMIT)!=png:raise ValueError('Saved chart identity changed.')
    return {k:image[k] for k in CHART_EVIDENCE_FIELDS}


def verify_chart_source(run,decision,image):
    from .project_history import restore_context
    context=restore_context(run,decision.get('cutoff'))
    source=image.get('source',{});kwargs={}
    if source.get('renderer')=='ohlcv-v2':
        manifest=run.get('frozen',{}).get('manifest',{});judgment=manifest.get('judgment') or {}
        kwargs['history_bars']=(judgment.get('history_bars') or manifest.get('history_bars')) if judgment.get('chart_history')=='declared' else 120
        if judgment.get('history_bars'):
            context=dict(context,bars={s:rows[-judgment['history_bars']:] for s,rows in context['bars'].items()})
        if source.get('candidate'):
            kwargs['candidate']=next((c for c in decision.get('proposal',{}).get('candidates',[]) if c['candidate_id']==source['candidate']['candidate_id']),None)
            if kwargs['candidate'] is None:raise ValueError('Unknown saved chart candidate.')
    original=restore_context(run,decision.get('cutoff'))
    if (not original or digest(original)!=decision.get('input_hash') or
        chart_source(context,source.get('symbol'),**kwargs)[1]!=source):
        raise ValueError('Saved chart provenance changed or source data is unavailable.')


def read_chart(store,pid,rid,sha256,run):
    if not re.fullmatch(r'[a-f0-9]{64}',sha256):raise ValueError('Invalid chart identity.')
    matches=[(d,image) for d in run.get('decisions',[]) for image in d.get('images',[]) if image['sha256']==sha256]
    if not matches:raise ValueError('Chart is not recorded in this run.')
    decision,image=matches[0];verify_chart_source(run,decision,image)
    path=store.path.parent/'project-run-images'/pid/rid/(sha256+'.png')
    return inspect_png(private_read(store.path.parent,path,OUTPUT_LIMIT),image)
