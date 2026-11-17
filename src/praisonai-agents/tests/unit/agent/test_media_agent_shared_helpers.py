"""G-30: AudioAgent, OCRAgent and VisionAgent share one copy of their helpers.

Characterisation test (passes before and after): the lazy ``console``,
``_configure_logging`` and ``_get_model_params`` behave the same on all three.
"""

import logging

import pytest

from praisonaiagents._logging import get_logger
from praisonaiagents.agent.audio_agent import AudioAgent
from praisonaiagents.agent.ocr_agent import OCRAgent
from praisonaiagents.agent.vision_agent import VisionAgent

CLASSES = [AudioAgent, OCRAgent, VisionAgent]


@pytest.mark.parametrize("cls", CLASSES)
def test_model_params(cls):
    agent = cls(model="openai/m1", api_key="k", base_url="http://local/v1")
    assert agent._get_model_params() == {"model": "openai/m1", "api_key": "k", "api_base": "http://local/v1"}
    assert agent._get_model_params("other") == {"model": "other", "api_key": "k", "api_base": "http://local/v1"}
    bare = cls(model="m2")
    bare.api_key = bare.base_url = None
    assert bare._get_model_params() == {"model": "m2"}


@pytest.mark.parametrize("cls", CLASSES)
def test_console_is_lazy_and_cached(cls):
    agent = cls(model="m")
    assert agent._console is None
    console = agent.console
    assert console is agent.console and agent._console is console


@pytest.mark.parametrize("cls", CLASSES)
def test_configure_logging_levels(cls):
    saved = {n: get_logger(n).level for n in ("litellm", "httpx")}
    try:
        agent = cls(model="m")
        agent._configure_logging(10)
        assert get_logger("litellm").level == logging.DEBUG
        agent._configure_logging(False)
        assert get_logger("litellm").level == logging.WARNING
        assert get_logger("httpx").level == logging.WARNING
    finally:
        for n, level in saved.items():
            get_logger(n).setLevel(level)
