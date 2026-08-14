"""Regression tests for the deprecated ``recipe serve`` command."""

import importlib
from unittest.mock import Mock

import pytest
import typer

from praisonai.cli.commands.recipe import recipe_serve
from praisonai.recipe.serve import create_app


def _invoke_recipe_serve(**overrides):
    options = {
        "recipe": None,
        "host": "127.0.0.1",
        "port": 8765,
        "reload": False,
        "workers": 1,
        "config": None,
        "api_key": None,
        "cors": "*",
        "metrics": False,
        "admin": False,
    }
    options.update(overrides)
    recipe_serve(**options)


def test_recipe_serve_initialises_config_before_auth_check(monkeypatch):
    serve = Mock()
    serve_module = importlib.import_module("praisonai.recipe.serve")
    monkeypatch.setattr(serve_module, "serve", serve)

    _invoke_recipe_serve()

    serve.assert_called_once()
    assert serve.call_args.kwargs["config"]["cors_origins"] == "*"


def test_recipe_serve_honours_auth_from_config(monkeypatch):
    serve = Mock()
    load_config = Mock(return_value={"auth": "api-key", "api_key": "configured"})
    serve_module = importlib.import_module("praisonai.recipe.serve")
    monkeypatch.setattr(serve_module, "serve", serve)
    monkeypatch.setattr(serve_module, "load_config", load_config)

    _invoke_recipe_serve(host="0.0.0.0", config="serve.yaml")

    load_config.assert_called_once_with("serve.yaml")
    serve.assert_called_once()
    assert serve.call_args.kwargs["config"]["auth"] == "api-key"
    assert serve.call_args.kwargs["config"]["api_key"] == "configured"


def test_recipe_serve_rejects_unsupported_auth_mode(monkeypatch):
    serve = Mock()
    load_config = Mock(return_value={"auth": "apikey", "api_key": "configured"})
    serve_module = importlib.import_module("praisonai.recipe.serve")
    monkeypatch.setattr(serve_module, "serve", serve)
    monkeypatch.setattr(serve_module, "load_config", load_config)

    with pytest.raises(typer.Exit):
        _invoke_recipe_serve(host="0.0.0.0", config="serve.yaml")

    load_config.assert_called_once_with("serve.yaml")
    serve.assert_not_called()


def test_recipe_serve_allows_jwt_auth_from_config(monkeypatch):
    serve = Mock()
    load_config = Mock(return_value={"auth": "jwt", "jwt_secret": "secret"})
    serve_module = importlib.import_module("praisonai.recipe.serve")
    monkeypatch.setattr(serve_module, "serve", serve)
    monkeypatch.setattr(serve_module, "load_config", load_config)

    _invoke_recipe_serve(host="0.0.0.0", config="serve.yaml")

    load_config.assert_called_once_with("serve.yaml")
    serve.assert_called_once()
    assert serve.call_args.kwargs["config"]["auth"] == "jwt"
    assert serve.call_args.kwargs["config"]["jwt_secret"] == "secret"


def test_recipe_server_rejects_unknown_auth_mode():
    with pytest.raises(ValueError, match="Unsupported recipe server auth mode"):
        create_app({"auth": "api-keey"})


@pytest.mark.parametrize("auth_mode", ["", False, []])
def test_recipe_server_rejects_falsey_invalid_auth_modes(auth_mode):
    with pytest.raises(ValueError, match="Unsupported recipe server auth mode"):
        create_app({"auth": auth_mode})
