# SDK Behavior Matrix

Deterministic expectations for the public knobs that integrators most often mistake for
"model randomness". Each row names the test that pins the behavior; if the test passes and
your app disagrees with the row, the row (or your call) is wrong — not the model.

- **Scope:** `praisonaiagents` Python API (main branch). Paths are relative to
  `src/praisonai-agents/`.
- **Source of truth:** code + the listed tests. If a docstring disagrees with this page,
  trust the test, then fix whichever is stale.

## How to use

1. Find the knob from the report in the tables below.
2. Run the listed test: `PYTHONPATH=. python -m pytest <test> -q`.
3. **Test fails** → SDK defect; open a bug. **Test passes** but behavior differs → check the
   *Sharp edge* column, then update this page if it is stale.

---

## 1. Chat & streaming

Streaming is configured through `output=`, not a constructor kwarg.
`Agent(stream=True)` raises `TypeError` with the hint
*"streaming moved into output=; use output=OutputConfig(stream=True)."*
`agent.stream` is `False` unless `output="stream"` or `OutputConfig(stream=True)` is used.

| API / knob | Expected behavior | Sharp edge | Test |
| --- | --- | --- | --- |
| `chat(prompt, stream=None)` | Inherits `agent.stream`. Returns the final `str` (or model, see §3). | Never a generator. | `tests/unit/agent/test_execution_api.py` |
| `chat(stream=True)` | Tokens go to `agent.stream_emitter`; the call still returns the full `str`. If the adapter cannot stream (`"Streaming is not supported"`) or the stream attempt fails transiently, it falls back to a non-streaming call. | `None` is **not** a valid "streaming succeeded" result (#5737). `LLMError`, `ToolExecutionError`, other `ValueError`s and post-dispatch tool-turn failures are raised, not retried. | `tests/test_chat_explicit_stream_fallback.py`, `tests/test_streaming_fallback_kwargs.py` |
| `chat(stream=False)` | Single non-streaming completion; no stream events. | — | `tests/unit/test_stream_preset.py` |
| `start(prompt)` | Stream priority: explicit kwarg > `agent.stream` > TTY. When streaming, returns a **generator** of chunks; otherwise a `str`. | Because `agent.stream` is always a bool, the TTY fallback only applies if `agent.stream` is set to `None`. Output guardrails are not applied to streamed chunks. | `tests/unit/agent/test_execution_api.py` |
| `run(prompt)` | Never streams unless `stream=True` is passed; returns `str`. | Ignores TTY. | `tests/unit/agent/test_execution_api.py::test_run_ignores_tty_detection` |
| `iter_stream(prompt)` | Always a generator of chunks. | — | `tests/unit/agent/test_execution_api.py::test_iter_stream_always_streams` |
| `achat()` / `astart()` | Same `stream` resolution as `chat()`; awaits and returns the final `str`. | Unlike `start()`, `astart()` never returns an (async) generator. | `tests/unit/agent/test_achat_unified_dispatch.py`, `tests/unit/agent/test_execution_api.py::test_astart_streams_in_tty` |

**When `chat()`/`achat()` return `None`:** input guardrail or `BEFORE_AGENT` hook blocked the
run, or the LLM call failed (history is rolled back and the error is displayed/logged).
An **output** guardrail rejection returns a fixed refusal string, not `None`; see
`agent.last_guardrail_error`.

## 2. Memory prefetch & scope

| API / knob | Expected behavior | Sharp edge | Test |
| --- | --- | --- | --- |
| `MemoryConfig(prefetch=True)` — sync (`_prefetch_memory`) | Before each turn, searches long-term memory with up to 5 terms (verbatim prompt → significant words → salient single words), stopping at the first non-empty hit. Results are injected into the **system prompt** under `## Recalled memories`, capped by `prefetch_limit` (5) and `prefetch_token_budget` (512, truncated with `…`). | Off by default. Errors are swallowed (debug log) and inject nothing. | `tests/unit/memory/test_prefetch.py` |
| Same — async (`_aprefetch_memory`) | Same terms, stop rule, scope and formatting via `asearch_memory`. | Backends with only `.search()` (no `search_long_term`) are searched by the sync path but not the async path. | `tests/unit/memory/test_prefetch.py::test_async_prefetch_falls_back_to_significant_tokens` |
| `MemoryConfig(user_id=...)` | Agents sharing a `user_id` share a store and recall each other's turns. Search is scoped by `user_id` + `session_id`, not `agent_id`. | Without `user_id`, each Agent gets a random `agent-<uuid>` id (warning logged) — memory is **isolated per instance**. There is no `Agent(user_id=...)` kwarg. | `tests/test_memory_cross_session.py` |

## 3. Structured output

`output_pydantic` / `output_json` are per-call `chat()`/`achat()` kwargs (forwarded by
`start()`/`run()`) and `Task` fields — not `Agent` constructor params. There is no
`output_json_schema`. Native `response_format` is used when the model supports structured
outputs; otherwise the schema is appended to the prompt as text.

| API / knob | Expected behavior | Sharp edge | Test |
| --- | --- | --- | --- |
| `chat(..., output_pydantic=Model)` | Returns a `Model` **instance** (tries strict JSON, fenced ```json, then first `{...}` in prose). | On parse failure, logs a warning and returns the **raw string** — no exception, no retry. Check `isinstance`. | `tests/unit/agents/test_chat_output_pydantic_coercion.py` |
| `chat(..., output_json=Model)` | Returns a JSON **string**. | Never a `dict` — call `json.loads` yourself. | `tests/unit/agents/test_chat_output_pydantic_coercion.py::test_chat_output_json_stays_string` |
| `Task(output_pydantic=Model)` in a team | `TaskOutput.pydantic` holds the instance; `output_format="Pydantic"`. | Fails closed: invalid output is a failed task (`Structured output validation failed ...`), which drives the retry loop. Setting both `output_json` and `output_pydantic` raises `ValueError`. | `tests/unit/agents/test_output_pydantic_policy.py` |
| `Task(output_json=Model)` in a team | `TaskOutput.json_dict` holds the parsed `dict`; `output_format="JSON"`. | Same fail-closed rule. | `tests/unit/agents/test_output_pydantic_policy.py::test_output_json_prose_is_not_success` |
| Native vs text schema | `response_format` (strict) for capable models; prompt injection otherwise. | Provider-dependent. | `tests/test_native_structured_outputs.py` |

## 4. Teams & handoff

| API / knob | Expected behavior | Sharp edge | Test |
| --- | --- | --- | --- |
| `AgentTeam(agents, tasks=[Task, ...])` | Accepts a list/tuple of `Task`. Sequential tasks are chained. `start()` returns the last task's `.raw` string (`return_dict=True` → `{"task_status", "task_results"}`). | `tasks="..."` → `TypeError: AgentTeam.tasks must be a list of Task instances, not str. ...`; `tasks=[]` → `ValueError: If tasks are provided, at least one task must be present`; non-`Task` item → `TypeError: tasks[i] must be a Task instance, got <type>`. | `tests/unit/agents/test_agentteam_task_validation.py` |
| `AgentTeam(agents)` (no tasks) | One task auto-generated per agent. | Empty `agents` fails at `start()`, not construction. | `tests/unit/agents/test_agentteam_task_validation.py::test_tasks_none_auto_generates` |
| `Agent(handoffs=[other])` | Adds a `transfer_to_<name>` tool; the model decides whether to call it. Tool returns `"Handoff successful. <name> response: ..."`. | The model may not call the tool — that is a prompt issue, not a crash. Cycles/depth (`max_depth=10`) return an `"Error: ..."` string to the model rather than raising. Timeout (300 s) applies to async handoffs only. | `tests/test_handoff_compatibility.py`, `tests/unit/test_handoff_unified.py` |

## 5. AG-UI

| API / knob | Expected behavior | Sharp edge | Test |
| --- | --- | --- | --- |
| `AGUI(agent=...).get_router()` | Returns a FastAPI `APIRouter`; mount it with `app.include_router(...)`. `POST {prefix}/agui` → SSE (`text/event-stream`); `GET {prefix}/status` → `{"status": "available"}`. | AGUI has no built-in server or default port — you run uvicorn and own startup/shutdown. `AGUI()` with no agent raises `ValueError`. | `tests/agui/test_agui.py`, `tests/agui/test_router.py` |
| SSE events | `RUN_STARTED` → `TEXT_MESSAGE_*` / `TOOL_CALL_*` → `RUN_FINISHED`; exceptions become `RUN_ERROR`. | Multi-agent (`agents=`) sends the whole result as one text message, not token stream. | `tests/agui/test_router.py::test_agui_endpoint_handles_agent_error` |

---

## Keeping this page in sync

- A PR that changes behavior of any API listed here updates the matching row (and its test)
  in the same PR.
- Intentional behavior that looks like a bug: keep it in *Sharp edge* with the issue number.
- Renamed/moved tests: update the *Test* column.
