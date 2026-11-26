"""Exercise Responses continuation through the real HTTP transport."""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from praisonaiagents.llm.llm import LLM


@pytest.fixture
def endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "local-test")
    monkeypatch.chdir(tmp_path)
    requests = []
    control = {"errors": [], "outputs": [], "auth": []}
    control["texts"] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["content-length"])))
            requests.append(request)
            control["auth"].append(self.headers.get("authorization"))
            number = len(requests)
            error = control["errors"].pop(0) if control["errors"] else None
            if error:
                status, detail = error
                body = json.dumps({"error": detail}).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            response = {
                "id": f"resp_{number}",
                "object": "response",
                "created_at": 0,
                "status": "completed",
                "model": "gpt-4o-mini",
                "output": [
                    {
                        "type": "message",
                        "id": f"msg_{number}",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "hello", "annotations": []}
                        ],
                    }
                ],
                "usage": {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
                "parallel_tool_calls": True,
                "tool_choice": "auto",
                "tools": [],
            }
            if control["texts"]:
                response["output"][0]["content"][0]["text"] = control["texts"].pop(0)
            if control["outputs"]:
                response["output"] = control["outputs"].pop(0)
            if request.get("stream"):
                events = []
                for index, item in enumerate(response["output"]):
                    if item["type"] == "function_call":
                        events.append(
                            {
                                "type": "response.output_item.done",
                                "output_index": index,
                                "item": item,
                            }
                        )
                    elif item["type"] == "message":
                        for part in item["content"]:
                            events.append(
                                {
                                    "type": "response.output_text.delta",
                                    "delta": part["text"],
                                }
                            )
                events.append({"type": "response.completed", "response": response})
                body = "".join(f"data: {json.dumps(e)}\n\n" for e in events).encode()
                content_type = "text/event-stream"
            else:
                body = json.dumps(response).encode()
                content_type = "application/json"
            self.send_response(200)
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_address[1]}/v1"
    monkeypatch.setenv("OPENAI_BASE_URL", base)
    monkeypatch.setenv("OPENAI_API_BASE", base)
    try:
        yield base, requests, control
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


@pytest.mark.parametrize("mode", ["sync", "async", "stream", "astream", "events"])
def test_reuses_response_with_only_new_input(endpoint, mode):
    base, requests, control = endpoint
    llm = LLM(
        model="gpt-4o-mini",
        api_key="local-test",
        base_url=base,
        server_side_conversation=True,
    )
    history = []

    def invoke(prompt):
        options = dict(
            chat_history=history,
            system_prompt="Answer briefly.",
            stream=mode in ("stream", "astream"),
            verbose=False,
        )
        if mode in ("async", "astream"):
            return asyncio.run(llm.get_response_async(prompt, **options))
        if mode == "events":
            options.pop("stream")
            return "".join(llm.get_response_stream(prompt, **options))
        return llm.get_response(prompt, **options)

    assert invoke("First question") == "hello"
    history.extend(
        [
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "hello"},
        ]
    )
    assert invoke("Second question") == "hello"
    assert requests[0]["store"] is True
    assert "previous_response_id" not in requests[0]
    assert requests[1]["previous_response_id"] == "resp_1"
    assert requests[1]["input"] == [{"role": "user", "content": "Second question"}]
    assert requests[1]["instructions"] == "Answer briefly."


def test_assistant_whitespace_does_not_break_a_matching_history_prefix(endpoint):
    base, requests, control = endpoint
    control["texts"].append("hello\n")
    llm = LLM(
        model="gpt-4o-mini",
        api_key="local-test",
        base_url=base,
        server_side_conversation=True,
    )
    answer = llm.get_response("First", stream=False, verbose=False)
    history = [
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": answer.strip()},
    ]
    llm.get_response("Second", chat_history=history, stream=False, verbose=False)
    assert requests[1]["previous_response_id"] == "resp_1"
    assert len(requests[1]["input"]) == 1


def test_rotating_provider_credentials_keep_separate_response_chains(endpoint):
    base, requests, control = endpoint
    llm = LLM(
        model="gpt-4o-mini",
        base_url=base,
        server_side_conversation=True,
    )
    assert (
        llm.get_response("First", api_key="account-a", stream=False, verbose=False)
        == "hello"
    )
    history = [
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": "hello"},
    ]
    assert (
        llm.get_response(
            "Second",
            chat_history=history,
            api_key="account-b",
            stream=False,
            verbose=False,
        )
        == "hello"
    )
    assert "previous_response_id" not in requests[1]
    assert len(requests[1]["input"]) == 3
    history.extend(
        [
            {"role": "user", "content": "Second"},
            {"role": "assistant", "content": "hello"},
        ]
    )
    assert (
        llm.get_response(
            "Third",
            chat_history=history,
            api_key="account-b",
            stream=False,
            verbose=False,
        )
        == "hello"
    )
    assert requests[2]["previous_response_id"] == "resp_2"
    assert len(requests[2]["input"]) == 1
    assert control["auth"] == [
        "Bearer account-a",
        "Bearer account-b",
        "Bearer account-b",
    ]


def test_yaml_agent_uses_the_same_continuation(endpoint):
    from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser

    base, requests, _ = endpoint
    parser = YAMLWorkflowParser()
    parser.parse_string("""
name: Continuation test
agents:
  assistant:
    instructions: Answer briefly.
    llm:
      model: gpt-4o-mini
      server_side_conversation: true
steps:
  - agent: assistant
    action: First
""")
    with parser._agents["assistant"] as agent:
        assert agent.start("First") == "hello"
        assert agent.start("Next") == "hello"
    assert requests[1]["previous_response_id"] == "resp_1"


def test_continuation_is_scoped_to_the_trace_session(endpoint):
    from praisonaiagents.trace.context_events import ContextTraceEmitter, trace_context

    base, requests, _ = endpoint
    llm = LLM(
        model="gpt-4o-mini",
        api_key="local-test",
        base_url=base,
        server_side_conversation=True,
    )
    with trace_context(ContextTraceEmitter(session_id="session-a")):
        llm.get_response("First", stream=False, verbose=False)
    history = [
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": "hello"},
    ]
    with trace_context(ContextTraceEmitter(session_id="session-b")):
        llm.get_response("Next", chat_history=history, stream=False, verbose=False)
    assert "previous_response_id" not in requests[1]


def test_store_false_and_explicit_continuation_are_preserved(endpoint):
    base, requests, _ = endpoint
    llm = LLM(
        model="gpt-4o-mini",
        api_key="local-test",
        base_url=base,
        server_side_conversation=True,
    )
    llm.get_response("First", store=False, stream=False, verbose=False)
    assert requests[0]["store"] is False
    llm.get_response(
        "Next", previous_response_id="caller_owned", stream=False, verbose=False
    )
    assert requests[1]["previous_response_id"] == "caller_owned"
    assert "store" not in requests[1]


def test_constructor_store_false_disables_reuse(endpoint):
    base, requests, _ = endpoint
    llm = LLM(
        model="gpt-4o-mini",
        api_key="local-test",
        base_url=base,
        server_side_conversation=True,
        store=False,
    )
    llm.get_response("First", stream=False, verbose=False)
    assert requests[0]["store"] is False


def test_environment_credential_change_starts_a_new_chain(endpoint, monkeypatch):
    base, requests, _ = endpoint
    llm = LLM(model="gpt-4o-mini", base_url=base, server_side_conversation=True)
    llm.get_response("First", stream=False, verbose=False)
    monkeypatch.setenv("OPENAI_API_KEY", "rotated-local-test")
    history = [
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": "hello"},
    ]
    llm.get_response("Next", chat_history=history, stream=False, verbose=False)
    assert "previous_response_id" not in requests[1]


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize("changed", ["credential", "agent"])
def test_stream_completion_keeps_its_original_identity(
    endpoint, monkeypatch, mode, changed
):
    base, requests, control = endpoint
    llm = LLM(model="gpt-4o-mini", base_url=base, server_side_conversation=True)
    llm.set_current_agent("first", "agent-a")
    params = llm._build_responses_params([{"role": "user", "content": "First"}])

    def change_identity(event):
        if changed == "credential":
            monkeypatch.setenv("OPENAI_API_KEY", "account-b")
        else:
            llm.set_current_agent("second", "agent-b")

    options = dict(stream_callback=change_identity, emit_events=True)
    if mode == "sync":
        result = llm._stream_responses_api(params, **options)
        assert result[0] == "hello"
    else:
        result = asyncio.run(llm._stream_responses_api_async(params, **options))
        assert result[0] == "hello"
        if changed == "agent":
            # asyncio.run keeps ContextVar changes inside its task.
            llm.set_current_agent("second", "agent-b")
    history = [
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": "hello"},
    ]
    llm.get_response("Next", chat_history=history, stream=False, verbose=False)
    assert "previous_response_id" not in requests[1]
    if changed == "credential":
        assert control["auth"] == ["Bearer local-test", "Bearer account-b"]
        monkeypatch.setenv("OPENAI_API_KEY", "local-test")
    else:
        llm.set_current_agent("first", "agent-a")
    llm.get_response("Next", chat_history=history, stream=False, verbose=False)
    assert requests[2]["previous_response_id"] == "resp_1"


@pytest.mark.parametrize("mode", ["sync", "async", "stream", "astream"])
@pytest.mark.parametrize("setting", ["constructor", "per_call"])
def test_unsupported_store_stays_disabled_with_explicit_store_true(
    endpoint, mode, setting
):
    base, requests, control = endpoint
    llm = LLM(
        model="gpt-4o-mini",
        api_key="local-test",
        base_url=base,
        server_side_conversation=True,
        max_retries=0,
        **({"store": True} if setting == "constructor" else {}),
    )
    control["errors"].append(
        (
            400,
            {
                "message": "Unsupported parameter: store",
                "type": "invalid_request_error",
                "param": "store",
                "code": "unsupported_parameter",
            },
        )
    )

    def invoke(prompt):
        options = dict(stream=mode in ("stream", "astream"), verbose=False)
        if setting == "per_call":
            options["store"] = True
        if mode in ("async", "astream"):
            return asyncio.run(llm.get_response_async(prompt, **options))
        return llm.get_response(prompt, **options)

    assert invoke("First") == "hello"
    assert invoke("Next") == "hello"
    assert requests[0]["store"] is True
    assert all("store" not in request for request in requests[1:])
    llm.get_response(
        "Explicit",
        previous_response_id="caller_owned",
        store=True,
        stream=False,
        verbose=False,
    )
    assert requests[-1]["previous_response_id"] == "caller_owned"
    assert requests[-1]["store"] is True


@pytest.mark.parametrize("status", [400, 401, 500])
def test_unrelated_provider_errors_do_not_trigger_full_replay(endpoint, status):
    from praisonaiagents.llm.llm import LLMResponseError

    base, requests, control = endpoint
    llm = LLM(
        model="gpt-4o-mini",
        api_key="local-test",
        base_url=base,
        server_side_conversation=True,
        max_retries=0,
    )
    control["errors"].append(
        (
            status,
            {
                "message": "Rejected request",
                "type": "invalid_request_error",
                "param": "input",
            },
        )
    )
    with pytest.raises(LLMResponseError, match="Rejected request"):
        llm.get_response("First", stream=False, verbose=False)
    assert len(requests) == 1


@pytest.mark.parametrize(
    "changed", ["disabled", "edit", "compact", "other_agent", "clone"]
)
def test_full_replay_when_continuation_does_not_apply(endpoint, changed):
    import copy

    base, requests, _ = endpoint
    llm = LLM(
        model="gpt-4o-mini",
        api_key="local-test",
        base_url=base,
        server_side_conversation=changed != "disabled",
    )
    llm.set_current_agent("first", "agent-a")
    assert llm.get_response("First", stream=False, verbose=False) == "hello"
    history = [
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": "hello"},
    ]
    if changed == "edit":
        history[0]["content"] = "Edited"
    elif changed == "compact":
        history = []
    elif changed == "other_agent":
        llm.set_current_agent("second", "agent-b")
    elif changed == "clone":
        llm = copy.deepcopy(llm)
    assert (
        llm.get_response("Next", chat_history=history, stream=False, verbose=False)
        == "hello"
    )
    assert "previous_response_id" not in requests[-1]
    assert len(requests[-1]["input"]) == len(history) + 1
    if changed == "disabled":
        assert "store" not in requests[0]


@pytest.mark.parametrize("mode", ["sync", "async", "stream", "astream"])
@pytest.mark.parametrize("failure", ["expired", "unsupported"])
def test_replays_once_when_provider_cannot_continue(endpoint, mode, failure):
    base, requests, control = endpoint
    llm = LLM(
        model="gpt-4o-mini",
        api_key="local-test",
        base_url=base,
        server_side_conversation=True,
        max_retries=0,
    )

    def invoke(prompt, history):
        kwargs = dict(
            chat_history=history, verbose=False, stream=mode in ("stream", "astream")
        )
        if mode in ("async", "astream"):
            return asyncio.run(llm.get_response_async(prompt, **kwargs))
        return llm.get_response(prompt, **kwargs)

    assert invoke("First", []) == "hello"
    history = [
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": "hello"},
    ]
    code = (
        "previous_response_not_found"
        if failure == "expired"
        else "unsupported_parameter"
    )
    param = "previous_response_id" if failure == "expired" else "store"
    status = 404 if failure == "expired" else 400
    control["errors"].append(
        (
            status,
            {
                "message": "Cannot continue",
                "type": "invalid_request_error",
                "code": code,
                "param": param,
            },
        )
    )
    assert invoke("Next", history) == "hello"
    assert len(requests) == 3
    assert requests[1]["previous_response_id"] == "resp_1"
    assert "previous_response_id" not in requests[2]
    assert len(requests[2]["input"]) == 3
    if failure == "unsupported":
        assert "store" not in requests[2]
    history.extend(
        [{"role": "user", "content": "Next"}, {"role": "assistant", "content": "hello"}]
    )
    assert invoke("Last", history) == "hello"
    if failure == "expired":
        assert requests[3]["previous_response_id"] == "resp_3"
    else:
        assert "store" not in requests[3]
        assert "previous_response_id" not in requests[3]


@pytest.mark.parametrize("mode", ["sync", "async", "stream", "astream"])
def test_tool_round_sends_only_the_paired_result(endpoint, mode):
    base, requests, control = endpoint
    control["outputs"].append(
        [
            {
                "type": "function_call",
                "id": "fc_1",
                "call_id": "call_1",
                "name": "lookup",
                "arguments": '{"value":7}',
                "status": "completed",
            }
        ]
    )
    llm = LLM(
        model="gpt-4o-mini",
        api_key="local-test",
        base_url=base,
        server_side_conversation=True,
    )
    calls = []

    def lookup(value: int) -> str:
        """Look up a record by its ID."""
        return f"found:{value}"

    def execute(name, arguments, tool_call_id=None):
        calls.append((name, arguments))
        return lookup(**arguments)

    kwargs = dict(
        tools=[lookup],
        execute_tool_fn=execute,
        verbose=False,
        stream=mode in ("stream", "astream"),
    )
    if mode in ("async", "astream"):
        answer = asyncio.run(llm.get_response_async("Look up record 7", **kwargs))
    else:
        answer = llm.get_response("Look up record 7", **kwargs)
    assert answer == "hello"
    assert calls == [("lookup", {"value": 7})]
    assert len(requests) == 2
    assert requests[1]["previous_response_id"] == "resp_1"
    assert requests[1]["input"] == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": json.dumps("found:7"),
        }
    ]
