"""Provider-specific wire adapters. Offline-tested contracts, not claims of account/model availability."""
import json
import os
import time
import re
from dataclasses import dataclass
from urllib.parse import urlparse
import httpx
from .contracts import Decision
from . import provider_io

MAX_RESPONSE_BYTES=32*1024*1024
MAX_RESPONSE_SECONDS=240


PROVIDERS = {
    'openai': dict(label='OpenAI', env='OPENAI_API_KEY', base='https://api.openai.com/v1', images=True, protocol='responses'),
    'anthropic': dict(label='Anthropic Claude', env='ANTHROPIC_API_KEY', base='https://api.anthropic.com/v1', images=True, protocol='messages'),
    'gemini': dict(label='Google Gemini', env='GEMINI_API_KEY', base='https://generativelanguage.googleapis.com/v1beta', images=True, protocol='gemini'),
    'deepseek': dict(label='DeepSeek', env='DEEPSEEK_API_KEY', base='https://api.deepseek.com', images=False, protocol='chat'),
    'qwen': dict(label='通义千问 Qwen', env='DASHSCOPE_API_KEY', base='https://dashscope.aliyuncs.com/compatible-mode/v1', images=True, protocol='chat'),
    'kimi': dict(label='Kimi / Moonshot', env='MOONSHOT_API_KEY', base='https://api.moonshot.cn/v1', images=True, protocol='chat'),
    'glm': dict(label='智谱 GLM', env='ZHIPU_API_KEY', base='https://open.bigmodel.cn/api/paas/v4', images=True, protocol='chat'),
    'doubao': dict(label='豆包 / 火山方舟', env='ARK_API_KEY', base='https://ark.cn-beijing.volces.com/api/v3', images=True, protocol='chat'),
}

TOOL = {
    'name': 'read_bars', 'description': 'Read up to 40 dated bars within this instrument and visible history. At most one call.',
    'parameters': {'type': 'object', 'properties': {k: {'type': 'string'} for k in ['symbol', 'start_date', 'end_date']},
                   'required': ['symbol', 'start_date', 'end_date'], 'additionalProperties': False},
}
INSPECT_TOOL = {
    'name':'inspect_candidate','description':'Inspect an offered fixed candidate: computed facts plus a cutoff-limited cup/handle/full zoom. Never changes dates or accesses files.',
    'parameters':{'type':'object','properties':{'candidate_id':{'type':'string'},
        'section':{'type':'string','enum':['cup','handle','full']}},
        'required':['candidate_id','section'],'additionalProperties':False},
}


class ProviderError(RuntimeError):
    def __init__(self, message, ambiguous=False):
        super().__init__(message)
        self.ambiguous = ambiguous


@dataclass
class Reply:
    text: str
    tool_calls: list
    usage: dict
    raw: dict
    elapsed: float = 0


def normalize_usage(provider, u):
    if provider == 'openai':
        return dict(input=u.get('input_tokens', 0), output=u.get('output_tokens', 0),
                    cached=(u.get('input_tokens_details') or {}).get('cached_tokens', 0),
                    reasoning=(u.get('output_tokens_details') or {}).get('reasoning_tokens', 0), cache_write=0)
    if provider == 'anthropic':
        cached = u.get('cache_read_input_tokens', 0)
        write = u.get('cache_creation_input_tokens', 0)
        return dict(input=u.get('input_tokens', 0)+cached+write, output=u.get('output_tokens', 0), cached=cached, reasoning=0, cache_write=write)
    if provider == 'gemini':
        thought = u.get('thoughtsTokenCount', 0)
        return dict(input=u.get('promptTokenCount', 0), output=u.get('candidatesTokenCount', 0)+thought,
                    cached=u.get('cachedContentTokenCount', 0), reasoning=thought, cache_write=0)
    return dict(input=u.get('prompt_tokens', 0), output=u.get('completion_tokens', 0),
                cached=(u.get('prompt_tokens_details') or {}).get('cached_tokens', u.get('prompt_cache_hit_tokens', 0)),
                reasoning=(u.get('completion_tokens_details') or {}).get('reasoning_tokens', 0), cache_write=0)


def endpoint(provider):
    p = PROVIDERS[provider]
    base = os.getenv(f'{provider.upper()}_BASE_URL', p['base']).rstrip('/')
    parsed = urlparse(base)
    default_host = urlparse(p['base']).hostname
    host = parsed.hostname or ''
    qwen_workspace = provider == 'qwen' and host.endswith('.maas.aliyuncs.com')
    qwen_region = provider == 'qwen' and host in {'dashscope-intl.aliyuncs.com', 'dashscope-us.aliyuncs.com', 'cn-hongkong.dashscope.aliyuncs.com'}
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.query or parsed.fragment or not (host == default_host or qwen_workspace or qwen_region):
        raise ProviderError('Endpoint must be an approved HTTPS provider host; no arbitrary key forwarding')
    return base


class Adapter:
    def __init__(self, provider, client=None):
        if provider not in PROVIDERS:
            raise ProviderError('Unknown provider')
        self.provider = provider
        self.spec = PROVIDERS[provider]
        self.client = client

    def build(self, config, context, history, allow_tools=True):
        p, image = self.provider, context.get('image') or next(iter(context.get('images') or []),None)
        if config.use_images and image and not self.spec['images']:
            raise ProviderError('This provider adapter has no verified image contract; explicitly choose text-only mode or another provider')
        schema = context.get('schema') or Decision.model_json_schema()
        use_image = config.use_images and bool(image)
        images=(context.get('images') or [image]) if use_image else []
        tools=context.get('tools',[TOOL,INSPECT_TOOL])
        use_tools = config.use_tools and allow_tools
        base = endpoint(p)
        if p == 'openai':
            content = [{'type': 'input_text', 'text': context['text']}]
            content += [{'type':'input_image','image_url':f'data:image/png;base64,{im}','detail':'high'} for im in images]
            body = dict(model=config.model, store=False,
                        instructions=context['system'], input=[{'role': 'user', 'content': content}]+history,
                        max_output_tokens=config.max_output_tokens,
                        text={'format': {'type': 'json_schema', 'name': context.get('schema_name','cup_decision'), 'schema': schema, 'strict': True}})
            effort = getattr(config,'reasoning_effort','low')
            if effort:
                body['reasoning']={'effort':effort}
            if use_tools:
                body.update(tools=[dict(type='function', strict=True, **t) for t in tools], parallel_tool_calls=False)
            return base+'/responses', body
        if p == 'anthropic':
            content = [{'type': 'text', 'text': context['text']}]
            content += [{'type':'image','source':{'type':'base64','media_type':'image/png','data':im}} for im in images]
            body = dict(model=config.model, system=context['system'], messages=[{'role': 'user', 'content': content}]+history,
                        max_tokens=config.max_output_tokens, output_config={'format': {'type': 'json_schema', 'schema': schema}})
            if use_tools:
                body['tools'] = [dict(name=t['name'],description=t['description'],input_schema=t['parameters']) for t in tools]
            return base+'/messages', body
        if p == 'gemini':
            parts = [{'text': context['text']}]
            parts += [{'inlineData':{'mimeType':'image/png','data':im}} for im in images]
            body = dict(systemInstruction={'parts': [{'text': context['system']}]},
                        contents=[{'role': 'user', 'parts': parts}]+history,
                        generationConfig={'responseMimeType': 'application/json', 'responseJsonSchema': schema,
                                          'maxOutputTokens': config.max_output_tokens})
            if use_tools:
                body['tools'] = [{'functionDeclarations': tools}]
            return base+f'/models/{config.model}:generateContent', body
        # Official domestic OpenAI-compatible chat endpoints, with separate configuration/keys.
        content = [{'type': 'text', 'text': context['text']}]
        content += [{'type':'image_url','image_url':{'url':f'data:image/png;base64,{im}'}} for im in images]
        system = context['system']+'\nReturn only JSON conforming to this schema:\n'+json.dumps(schema)
        body = dict(model=config.model, messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': content}]+history,
                    max_tokens=config.max_output_tokens, stream=False, response_format={'type': 'json_object'})
        if use_tools:
            body['tools'] = [{'type':'function','function':t} for t in tools]
            body['tool_choice'] = 'auto'
        return base+'/chat/completions', body

    def count_input_tokens(self, body, key):
        """Count this exact OpenAI input without creating a model response.

        No retries, redirects, output generation, or reflected provider errors.
        Caller must already have authority to send this input to this connection.
        """
        if self.provider!='openai' or not key:
            raise ProviderError('Input counting requires the configured OpenAI connection.')
        fields={'model','input','instructions','tools','tool_choice','parallel_tool_calls',
                'reasoning','text','truncation','conversation','previous_response_id','personality'}
        if set(body)-fields-{'store','max_output_tokens'}:
            raise ProviderError('Unsupported input-counting payload; no model request sent.')
        payload={k:v for k,v in body.items() if k in fields}
        url=endpoint(self.provider)+'/responses/input_tokens'
        own=self.client is None
        client=self.client or httpx.Client(timeout=httpx.Timeout(5,write=10),follow_redirects=False)
        deadline=time.monotonic()+20
        try:
            try:
                with client.stream('POST',url,json=payload,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','Accept-Encoding':'identity'}) as response:
                    if response.status_code!=200:
                        raise ProviderError(f'Input token count unavailable (HTTP {response.status_code}); no model request sent.')
                    if response.headers.get('content-encoding','identity').strip().lower()!='identity':
                        raise ProviderError('Unsupported input token count encoding; no model request sent.')
                    raw=bytearray()
                    # Unaggregated reads let the deadline observe trickled bytes; never decompress.
                    # A stalled read is additionally bounded by the five-second read timeout.
                    for chunk in response.iter_raw():
                        if time.monotonic()>deadline:
                            raise ProviderError('Input token count deadline exceeded; no model request sent.')
                        if len(raw)+len(chunk)>16384:
                            raise ProviderError('Input token count response exceeds limit; no model request sent.')
                        raw.extend(chunk)
                value=json.loads(raw)
            except (httpx.HTTPError,ValueError):
                raise ProviderError('Input token count unavailable; no model request sent.') from None
            count=value.get('input_tokens') if isinstance(value,dict) else None
            if not isinstance(value,dict) or value.get('object')!='response.input_tokens' or type(count) is not int or not 0<count<=10000000:
                raise ProviderError('Invalid input token count; no model request sent.')
            return count
        finally:
            if own:client.close()

    def send(self, config, context, history, key, allow_tools=True, save_raw=None):
        if not key:
            raise ProviderError(f'Missing {self.spec["env"]}; no request sent')
        url, body = self.build(config, context, history, allow_tools)
        headers = {'Content-Type': 'application/json','Accept-Encoding':'identity'}
        if self.provider == 'anthropic':
            headers.update({'x-api-key': key, 'anthropic-version': '2023-06-01'})
        elif self.provider == 'gemini':
            headers['x-goog-api-key'] = key
        else:
            headers['Authorization'] = 'Bearer '+key
        started = time.monotonic()
        own = self.client is None
        client = self.client or httpx.Client(timeout=120, follow_redirects=False)
        try:
            try:
                with client.stream('POST',url,json=body,headers=headers) as response:
                    payload=bytearray()
                    for chunk in provider_io.chunks(response,limit=MAX_RESPONSE_BYTES,deadline=started+MAX_RESPONSE_SECONDS):payload.extend(chunk)
            except (httpx.HTTPError,ValueError):
                raise ProviderError('Transport outcome unknown; response may have been billed. Explicit acknowledgment required before retry.', ambiguous=True) from None
            if response.status_code >= 300:
                diagnostic=[]
                try:
                    error=json.loads(payload).get('error',{})
                    if isinstance(error,dict):
                        for field in ['type','code','param']:
                            value=error.get(field)
                            if isinstance(value,str) and key not in value and re.fullmatch(r'[A-Za-z0-9_.\[\]-]{1,120}',value):
                                diagnostic.append(f'{field}={value}')
                except (ValueError,AttributeError):
                    pass
                detail='; '.join(diagnostic) or 'response body withheld'
                raise ProviderError(f'{self.spec["label"]} HTTP {response.status_code}; {detail}', ambiguous=response.status_code >= 500)
            try:
                raw = json.loads(payload)
            except ValueError:
                raise ProviderError('Provider returned non-JSON; billing outcome unknown', ambiguous=True) from None
            elapsed = time.monotonic()-started
            # Persist before parsing/refusal/schema handling. Never include request auth.
            if save_raw:
                save_raw(raw, elapsed)
            reply = self.parse(raw)
            reply.elapsed = elapsed
            return reply
        finally:
            if own:
                client.close()

    def parse(self, raw):
        p = self.provider
        text, calls = '', []
        if p == 'openai':
            if raw.get('status') != 'completed':
                raise ProviderError('OpenAI response incomplete/refused; saved for inspection')
            for item in raw.get('output', []):
                if item.get('type') == 'function_call':
                    calls.append(dict(id=item['call_id'], name=item['name'], arguments=item['arguments']))
                for content in item.get('content', []):
                    if content.get('type') == 'refusal':
                        raise ProviderError('Model refusal; not a strategy rejection')
                    if content.get('type') == 'output_text':
                        text += content['text']
            u = raw.get('usage') or {}
        elif p == 'anthropic':
            if raw.get('stop_reason') not in {'end_turn', 'tool_use'}:
                raise ProviderError('Claude response stopped without a complete decision')
            for item in raw.get('content', []):
                if item['type'] == 'text':
                    text += item['text']
                if item['type'] == 'tool_use':
                    calls.append(dict(id=item['id'], name=item['name'], arguments=item['input']))
            u = raw.get('usage') or {}
        elif p == 'gemini':
            candidate = (raw.get('candidates') or [{}])[0]
            if candidate.get('finishReason') != 'STOP':
                raise ProviderError('Gemini response blocked/incomplete')
            for part in candidate.get('content', {}).get('parts', []):
                if not part.get('thought'):
                    text += part.get('text', '')
                if 'functionCall' in part:
                    tool = part['functionCall']
                    calls.append(dict(id=tool.get('id', tool['name']), name=tool['name'], arguments=tool.get('args', {})))
            u = raw.get('usageMetadata') or {}
        else:
            item = (raw.get('choices') or [{}])[0]
            if item.get('finish_reason') not in {'stop', 'tool_calls'}:
                raise ProviderError('Chat response incomplete/refused')
            message = item.get('message') or {}
            if message.get('refusal'):
                raise ProviderError('Model refusal')
            text = message.get('content') or ''
            for tool in message.get('tool_calls') or []:
                calls.append(dict(id=tool['id'], name=tool['function']['name'], arguments=tool['function']['arguments']))
            u = raw.get('usage') or {}
        if not text and not calls:
            raise ProviderError('No text or tool call returned')
        return Reply(text, calls, normalize_usage(p, u), raw)

    def followup(self, reply, results):
        images=[r['_image'] for r in results if r.get('_image') and self.spec['images']]
        results=[{k:v for k,v in r.items() if k!='_image'} for r in results]
        if self.provider == 'openai':
            history=reply.raw['output']+[{'type':'function_call_output','call_id':c['id'],'output':json.dumps(r)} for c,r in zip(reply.tool_calls,results)]
            if images:history.append({'role':'user','content':[{'type':'input_image','image_url':f'data:image/png;base64,{im}','detail':'high'} for im in images]})
            return history
        if self.provider == 'anthropic':
            return [{'role': 'assistant', 'content': reply.raw['content']}, {'role': 'user', 'content': [
                {'type':'tool_result','tool_use_id':c['id'],'content':json.dumps(r)} for c,r in zip(reply.tool_calls,results)]+
                [{'type':'image','source':{'type':'base64','media_type':'image/png','data':im}} for im in images]}]
        if self.provider == 'gemini':
            return [reply.raw['candidates'][0]['content'], {'role': 'user', 'parts': [
                {'functionResponse':{'name':c['name'],'response':r}} for c,r in zip(reply.tool_calls,results)]+
                [{'inlineData':{'mimeType':'image/png','data':im}} for im in images]}]
        history=[reply.raw['choices'][0]['message']]+[{'role':'tool','tool_call_id':c['id'],'content':json.dumps(r)} for c,r in zip(reply.tool_calls,results)]
        if images:history.append({'role':'user','content':[{'type':'image_url','image_url':{'url':f'data:image/png;base64,{im}'}} for im in images]})
        return history

    def correction(self, text):
        if self.provider == 'gemini':
            return {'role': 'user', 'parts': [{'text': text}]}
        return {'role': 'user', 'content': text}

    def assistant_items(self,reply):
        if self.provider=='openai':return reply.raw['output']
        if self.provider=='anthropic':return [{'role':'assistant','content':reply.raw['content']}]
        if self.provider=='gemini':return [reply.raw['candidates'][0]['content']]
        return [reply.raw['choices'][0]['message']]
