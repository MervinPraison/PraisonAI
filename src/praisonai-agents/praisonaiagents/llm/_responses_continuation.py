"""Opt-in, bounded continuation state for outbound Responses requests."""

import hashlib
import json
import os
import threading
from collections import OrderedDict

from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


def _get(value, key, default=None):
    return (
        value.get(key, default)
        if isinstance(value, dict)
        else getattr(value, key, default)
    )


def _fingerprints(items):
    result = []
    for item in items:
        item = dict(item)
        content = item.get("content")
        if isinstance(content, str):
            if item.get("role") == "assistant":
                content = content.strip()
            content = [{"type": "input_text", "text": content}]
        if isinstance(content, list):
            item["content"] = [
                (
                    {"type": "input_text", "text": part["text"]}
                    if isinstance(part, dict)
                    and part.get("type") in ("text", "input_text", "output_text")
                    else part
                )
                for part in content
            ]
        result.append(
            hashlib.sha256(json.dumps(item, sort_keys=True).encode()).digest()
        )
    return tuple(result)


class ResponsesContinuation:
    def __init__(self):
        self._states = OrderedDict()
        self._lock = threading.Lock()

    def prepare(self, params, scope):
        if (
            params.get("store") is False
            or params.get("conversation")
            or params.get("previous_response_id")
        ):
            return None
        identity = {
            k: params.get(k)
            for k in (
                "model",
                "api_base",
                "base_url",
                "api_version",
                "api_key",
                "user",
                "extra_headers",
                "metadata",
                "organization",
                "project",
            )
        }
        identity["environment"] = {
            name: os.environ.get(name)
            for name in (
                "OPENAI_API_KEY",
                "OPENAI_API_BASE",
                "OPENAI_BASE_URL",
                "OPENAI_ORG_ID",
                "OPENAI_ORGANIZATION",
                "OPENAI_PROJECT_ID",
                "AZURE_API_KEY",
                "AZURE_OPENAI_API_KEY",
                "AZURE_API_BASE",
                "AZURE_API_VERSION",
            )
        }
        key = (
            scope,
            hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).digest(),
        )
        with self._lock:
            state = self._states.get(key)
            if state is False:
                params.pop("store", None)
                return None
        return _Request(self, key, params, state)

    def save(self, key, state):
        with self._lock:
            self._states[key] = state
            self._states.move_to_end(key)
            while len(self._states) > 64:
                self._states.popitem(last=False)


class _Request:
    def __init__(self, owner, key, params, state):
        self.owner, self.key = owner, key
        self.full = dict(params)
        inputs = params.get("input", [])
        self.remember = isinstance(inputs, list)
        self.prefix = _fingerprints(inputs) if self.remember else ()
        self.params = {**params, "store": True} if self.remember else dict(params)
        if state and self.remember:
            response_id, prefix = state
            if len(self.prefix) > len(prefix) and self.prefix[: len(prefix)] == prefix:
                self.params["previous_response_id"] = response_id
                self.params["input"] = params["input"][len(prefix) :]

    def fallback(self, error):
        body = getattr(error, "body", None) or {}
        # Some LiteLLM adapters retain the provider's JSON only in the message.
        if not body:
            message = str(getattr(error, "message", error))
            start = message.find("{")
            if start >= 0:
                try:
                    body = json.JSONDecoder().raw_decode(message[start:])[0]
                except ValueError:
                    logger.debug("Continuation error did not contain a JSON body")
        detail = _get(body, "error", body)
        param = getattr(error, "param", None) or _get(detail, "param")
        code = getattr(error, "code", None) or _get(detail, "code")
        if getattr(error, "status_code", None) not in (400, 404, 422):
            return None
        message = str(_get(detail, "message", "")).lower()
        if not param and any(
            word in message for word in ("not support", "unsupported", "unrecognized")
        ):
            param = next(
                (name for name in ("store", "previous_response_id") if name in message),
                None,
            )
        if (
            param not in ("store", "previous_response_id")
            and code != "previous_response_not_found"
        ):
            return None
        self.owner.save(self.key, None)
        missing = code == "previous_response_not_found" or (
            param == "previous_response_id"
            and (getattr(error, "status_code", None) == 404 or "not found" in message)
        )
        if missing and "previous_response_id" in self.params:
            logger.debug("Stored response expired; replaying the full input")
            self.params = {**self.full, "store": True}
        else:
            self.remember = False
            logger.info(
                "Responses continuation disabled: provider rejected %s", param or code
            )
            self.owner.save(self.key, False)
            self.params = dict(self.full)
            self.params.pop("store", None)
        return self.params

    def call(self, function):
        try:
            return function(**self.params)
        except Exception as error:
            if self.fallback(error) is None:
                raise
            return function(**self.params)

    async def acall(self, function):
        try:
            return await function(**self.params)
        except Exception as error:
            if self.fallback(error) is None:
                raise
            return await function(**self.params)

    def complete(self, response, output):
        if not self.remember:
            return
        response_id = _get(response, "id")
        if not response_id or _get(response, "status") != "completed":
            self.owner.save(self.key, None)
            return
        self.owner.save(
            self.key,
            (response_id, self.prefix + _fingerprints(output)) if output else None,
        )
