import json
import httpx
import pytest

from lab.providers import PROVIDERS, Adapter, ProviderError, normalize_usage
from lab.contracts import RunConfig, Decision
from lab.prompts import make_context, tool_result
from tests.test_domain import bars


def config(provider):
    return RunConfig(provider=provider, model='test-model', use_images=provider != 'deepseek')


@pytest.mark.parametrize('provider', ['openai', 'anthropic', 'gemini', 'deepseek', 'qwen', 'kimi', 'glm', 'doubao'])
def test_all_adapters_send_native_requests_and_parse_text(provider):
    c = config(provider)
    context = {'system': 'approved method', 'text': 'Return JSON', 'image': 'aGVsbG8='}
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        assert 'secret-test-value' not in request.content.decode()
        if provider == 'openai':
            body = {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': '{"ok":true}'}]}], 'usage': {'input_tokens': 100, 'output_tokens': 20, 'output_tokens_details': {'reasoning_tokens': 10}}}
        elif provider == 'anthropic':
            body = {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': '{"ok":true}'}], 'usage': {'input_tokens': 100, 'output_tokens': 20}}
        elif provider == 'gemini':
            body = {'candidates': [{'finishReason': 'STOP', 'content': {'role': 'model', 'parts': [{'text': '{"ok":true}'}]}}], 'usageMetadata': {'promptTokenCount': 100, 'candidatesTokenCount': 10, 'thoughtsTokenCount': 10}}
        else:
            body = {'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': '{"ok":true}'}}], 'usage': {'prompt_tokens': 100, 'completion_tokens': 20}}
        return httpx.Response(200, json=body)
    adapter = Adapter(provider, httpx.Client(transport=httpx.MockTransport(handler)))
    reply = adapter.send(c, context, [], 'secret-test-value')
    assert json.loads(reply.text) == {'ok': True}
    assert reply.usage['input'] == 100 and reply.usage['output'] == 20
    assert reply.raw
    payload = seen[0]
    assert payload['model'] == 'test-model' if provider != 'gemini' else 'contents' in payload
    assert 'aGVsbG8=' in json.dumps(payload) if c.use_images else 'aGVsbG8=' not in json.dumps(payload)


def test_openai_strict_schema_low_reasoning_and_no_store():
    a = Adapter('openai')
    _, payload = a.build(RunConfig(), {'system': 'x', 'text': 'y', 'image': 'img'}, [])
    assert payload['store'] is False
    assert payload['reasoning']['effort'] == 'low'
    assert payload['parallel_tool_calls'] is False
    assert payload['text']['format']['strict'] is True
    assert payload['text']['format']['schema']['additionalProperties'] is False


@pytest.mark.parametrize('provider', list(PROVIDERS))
def test_provider_errors_never_echo_secret_or_untrusted_body(provider):
    def handler(r):
        return httpx.Response(401, text='bad key secret-test-value')
    a = Adapter(provider, httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ProviderError) as e:
        a.send(config(provider), {'system': '', 'text': '', 'image': 'img'}, [], 'secret-test-value')
    assert 'secret-test-value' not in str(e.value) and '401' in str(e.value)


def test_timeout_is_ambiguous_and_never_automatically_retries():
    hits = []
    def handler(r):
        hits.append(1)
        raise httpx.ReadTimeout('contains secret')
    a = Adapter('openai', httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ProviderError) as e:
        a.send(RunConfig(), {'system': '', 'text': '', 'image': ''}, [], 'secret')
    assert e.value.ambiguous and len(hits) == 1 and 'contains secret' not in str(e.value)


def test_deepseek_image_requires_capability_not_silent_omission():
    with pytest.raises(ProviderError, match='image'):
        Adapter('deepseek').build(RunConfig(provider='deepseek', model='deepseek-flash'), {'system': '', 'text': '', 'image': 'img'}, [])


def test_no_double_count_reasoning_and_cached_tokens():
    u = normalize_usage('openai', {'input_tokens': 100, 'output_tokens': 50,
                                 'input_tokens_details': {'cached_tokens': 30},
                                 'output_tokens_details': {'reasoning_tokens': 40}})
    assert u == {'input': 100, 'output': 50, 'cached': 30, 'reasoning': 40, 'cache_write': 0}
    u = normalize_usage('gemini', {'promptTokenCount': 100, 'candidatesTokenCount': 10, 'thoughtsTokenCount': 40})
    assert u['output'] == 50
    u = normalize_usage('anthropic', {'input_tokens': 10, 'cache_read_input_tokens': 80, 'cache_creation_input_tokens': 10, 'output_tokens': 3})
    assert u['input'] == 100 and u['cache_write'] == 10


def test_tool_roundtrip_preserves_native_reasoning_and_tool_call():
    a = Adapter('openai')
    reply = a.parse({'status': 'completed', 'output': [{'type': 'reasoning', 'id': 'r', 'summary': [], 'encrypted_content':'encrypted'},
                     {'type': 'function_call', 'call_id': 'c', 'name': 'read_bars', 'arguments': '{"symbol":"AAPL"}'}], 'usage': {}})
    history = a.followup(reply, [{'ok': True}])
    assert history[0]['type'] == 'reasoning'
    assert history[0]['encrypted_content'] == 'encrypted'
    assert history[-1] == {'type': 'function_call_output', 'call_id': 'c', 'output': '{"ok": true}'}


@pytest.mark.parametrize('provider,body', [
    ('openai', {'status': 'incomplete', 'output': []}),
    ('anthropic', {'stop_reason': 'max_tokens', 'content': []}),
    ('gemini', {'candidates': [{'finishReason': 'MAX_TOKENS', 'content': {'parts': []}}]}),
    ('qwen', {'choices': [{'finish_reason': 'length', 'message': {'content': 'half'}}]})])
def test_truncation_and_refusal_cannot_be_success(provider, body):
    with pytest.raises(ProviderError):
        Adapter(provider).parse(body)


def test_context_tool_cannot_fetch_future_data():
    b = bars()
    ctx = make_context('AAPL', b[:180], 179, RunConfig())
    assert b[180].date not in ctx['text']
    result = tool_result({'name': 'read_bars', 'arguments': {'symbol': 'AAPL', 'start_date': b[179].date, 'end_date': b[180].date}}, 'AAPL', b[:180])
    assert 'error' in result
