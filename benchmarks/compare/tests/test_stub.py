import json
import urllib.request

import pytest


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return r.read().decode()


def _stats(url):
    with urllib.request.urlopen(url + "/_stats") as r:
        return json.loads(r.read())


MSG = [{"role": "user", "content": "hi"}]


def test_nonce_increments_and_reset(stub):
    url, _ = stub
    a = json.loads(_post(url + "/v1/chat/completions", {"model": "m", "messages": MSG}))
    b = json.loads(_post(url + "/v1/chat/completions", {"model": "m", "messages": [
        {"role": "user", "content": a["choices"][0]["message"]["content"]}]}))
    assert a["choices"][0]["message"]["content"] == "Final Answer: NONCE-0001 done."
    assert "NONCE-0002" in b["choices"][0]["message"]["content"]
    s = _stats(url)
    assert s["count_by_path"] == {"/v1/chat/completions": 2}
    assert [r["has_prev_nonce"] for r in s["requests"]] == [None, True]
    assert s["bytes_total"] == sum(r["bytes"] for r in s["requests"])
    _post(url + "/_reset", {})
    assert _stats(url)["requests"] == []
    c = json.loads(_post(url + "/v1/chat/completions", {"model": "m", "messages": MSG}))
    assert "NONCE-0001" in c["choices"][0]["message"]["content"]


def test_raw_sse_has_done_and_usage(stub):
    url, _ = stub
    body = _post(url + "/v1/chat/completions", {"model": "m", "messages": MSG, "stream": True,
                                                "stream_options": {"include_usage": True}})
    events = [ln[6:] for ln in body.splitlines() if ln.startswith("data: ")]
    assert events[-1] == "[DONE]"
    chunks = [json.loads(e) for e in events[:-1]]
    assert "".join(c["choices"][0]["delta"].get("content") or "" for c in chunks
                   if c["choices"]) == "Final Answer: NONCE-0001 done."
    assert chunks[-1]["usage"]["total_tokens"] == 15
    assert _stats(url)["requests"][0]["stream"] is True


def test_tool_call_script(stub):
    url, _ = stub
    tools = [{"type": "function", "function": {"name": "get_weather", "parameters": {
        "type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]
    first = json.loads(_post(url + "/v1/chat/completions",
                             {"model": "m", "messages": MSG, "tools": tools}))
    call = first["choices"][0]["message"]["tool_calls"][0]
    assert first["choices"][0]["finish_reason"] == "tool_calls"
    assert call["function"]["name"] == "get_weather"
    assert json.loads(call["function"]["arguments"]) == {"city": "x"}
    second = json.loads(_post(url + "/v1/chat/completions", {"model": "m", "tools": tools, "messages": [
        *MSG, first["choices"][0]["message"],
        {"role": "tool", "tool_call_id": "call_stub", "content": "Sunny"}]}))
    assert second["choices"][0]["message"]["content"].endswith("NONCE-0001 done.")


def test_models_endpoint(stub):
    url, _ = stub
    with urllib.request.urlopen(url + "/v1/models") as r:
        assert json.loads(r.read())["data"][0]["id"] == "gpt-4o-mini"


openai = pytest.importorskip("openai")


def test_openai_sdk_non_streaming(stub):
    url, _ = stub
    client = openai.OpenAI(base_url=url + "/v1", api_key="sk-stub")
    r = client.chat.completions.create(model="gpt-4o-mini", messages=MSG)
    assert r.choices[0].message.content == "Final Answer: NONCE-0001 done."
    assert r.usage.total_tokens == 15


def test_openai_sdk_streaming(stub):
    url, _ = stub
    client = openai.OpenAI(base_url=url + "/v1", api_key="sk-stub")
    chunks = list(client.chat.completions.create(model="gpt-4o-mini", messages=MSG, stream=True,
                                                 stream_options={"include_usage": True}))
    text = "".join(c.choices[0].delta.content or "" for c in chunks if c.choices)
    assert text == "Final Answer: NONCE-0001 done."
    assert chunks[-1].usage.total_tokens == 15


def test_openai_sdk_responses(stub):
    url, _ = stub
    client = openai.OpenAI(base_url=url + "/v1", api_key="sk-stub")
    r = client.responses.create(model="gpt-4o-mini", input="hi")
    assert r.output_text == "Final Answer: NONCE-0001 done."
    assert _stats(url)["count_by_path"] == {"/v1/responses": 1}
