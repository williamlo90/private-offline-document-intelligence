"""HTTP transport doubles only; no Ollama daemon/model is started."""
import asyncio
import json
from threading import Timer
import httpx
import pytest
from backend.domain import DomainError
from backend.ollama_adapter import OllamaGenerator, OllamaProfile, PROMPT_SHA256, _slot


def profile(**overrides):
    return OllamaProfile(schema_version='1.0', dedicated_runtime=True, port=11439,
                         model='fixture:small', digest='a'*64, prompt_sha256=PROMPT_SHA256, **overrides)


def runtime(*, digest='a'*64, busy=False, generate=None):
    calls=[]
    async def handle(request):
        calls.append(request)
        assert request.url.host=='127.0.0.1'
        if request.url.path=='/api/tags':
            return httpx.Response(200,json={'models':[{'name':'fixture:small','digest':digest,'details':{'format':'gguf'}}]})
        if request.url.path=='/api/ps':return httpx.Response(200,json={'models':[{}] if busy else []})
        assert request.url.path=='/api/generate'
        if generate:return await generate(request)
        return httpx.Response(200,json={'model':'fixture:small','done':True,'done_reason':'stop',
                                       'response':json.dumps({'status':'abstain','selections':[]})})
    return httpx.MockTransport(handle), calls


def invoke(adapter):
    return adapter.generate('answer_client_question',{'question':'Response?','evidence':{}},{'type':'object'})


def test_pinned_loopback_request_and_no_retry():
    transport,calls=runtime()
    adapter=OllamaGenerator(profile(),transport=transport,memory=lambda:8*1024**3)
    assert invoke(adapter)['status']=='abstain'
    sent=json.loads(calls[2].content)
    assert sent['keep_alive']==0 and sent['stream'] is False
    assert sent['options']['num_predict']==2048
    assert [r.url.path for r in calls]==['/api/tags','/api/ps','/api/generate','/api/tags']
    assert not adapter.uncertain


@pytest.mark.parametrize('kwargs,code',[({'digest':'b'*64},'native_model_pin_mismatch'),({'busy':True},'native_runtime_busy')])
def test_preflight_rejects_pin_or_loaded_models(kwargs,code):
    transport,calls=runtime(**kwargs)
    with pytest.raises(DomainError) as error:
        invoke(OllamaGenerator(profile(),transport=transport,memory=lambda:8*1024**3))
    assert error.value.code==code
    assert not any(r.url.path=='/api/generate' for r in calls)


def test_memory_and_single_inference_guard():
    transport,calls=runtime()
    adapter=OllamaGenerator(profile(),transport=transport,memory=lambda:0)
    with pytest.raises(DomainError) as error:invoke(adapter)
    assert error.value.code=='resource_budget_unavailable' and not calls
    _slot.acquire()
    try:
        with pytest.raises(DomainError) as error:invoke(adapter)
        assert error.value.code=='inference_busy'
    finally:_slot.release()


def test_bounded_peak_request_waits_for_single_inference_slot():
    transport,calls=runtime()
    adapter=OllamaGenerator(profile(),transport=transport,memory=lambda:8*1024**3,
                            queue_wait_seconds=.5)
    _slot.acquire()
    release=Timer(.05,_slot.release)
    release.start()
    try:
        assert invoke(adapter)['status']=='abstain'
        assert any(r.url.path=='/api/generate' for r in calls)
    finally:
        release.join()


@pytest.mark.parametrize('mode,code',[('timeout','native_model_timeout'),('large','model_response_limit'),('truncated','invalid_model_response'),('redirect','native_model_unavailable')])
def test_uncertain_generation_latches_until_operator_recovery(mode,code):
    async def generate(request):
        if mode=='timeout':await asyncio.sleep(1)
        if mode=='large':return httpx.Response(200,content=b'x'*256001)
        if mode=='redirect':return httpx.Response(307,headers={'Location':'https://example.com'})
        return httpx.Response(200,json={'model':'fixture:small','done':True,'done_reason':'length','response':'{}'})
    transport,calls=runtime(generate=generate)
    adapter=OllamaGenerator(profile(timeout_seconds=.05),transport=transport,memory=lambda:8*1024**3)
    with pytest.raises(DomainError) as error:invoke(adapter)
    assert error.value.code==code and adapter.uncertain
    count=len(calls)
    with pytest.raises(DomainError) as error:invoke(adapter)
    assert error.value.code=='native_runtime_needs_recovery' and len(calls)==count


def test_runtime_memory_drop_cancels_request():
    transport,calls=runtime()
    readings=iter([8*1024**3, 0])
    adapter=OllamaGenerator(profile(),transport=transport,memory=lambda:next(readings))
    with pytest.raises(DomainError) as error:invoke(adapter)
    assert error.value.code=='runtime_memory_reserve' and adapter.uncertain
