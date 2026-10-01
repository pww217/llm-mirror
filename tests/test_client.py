from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from llm_mirror.client import (
    ChatRequest,
    OmlxClient,
    OmlxClientError,
    TransientOmlxError,
)


def _make_client(sleep_calls: list | None = None) -> OmlxClient:
    calls: list[float] = sleep_calls if sleep_calls is not None else []
    return OmlxClient("http://localhost:8000/v1", sleep=calls.append)


def _make_response(status: int, json_data: dict | None = None) -> httpx.Response:
    req = httpx.Request("POST", "http://localhost/v1/chat/completions")
    return httpx.Response(status, request=req, json=json_data)


def _make_get_response(status: int, json_data: dict | None = None) -> httpx.Response:
    req = httpx.Request("GET", "http://localhost/health")
    return httpx.Response(status, request=req, json=json_data)


def _success_body() -> dict:
    return {
        "choices": [{"message": {"content": "I think cars are fine.", "role": "assistant"}}],
        "usage": {
            "prompt_tokens": 150,
            "completion_tokens": 50,
            "prompt_tokens_details": {"cached_tokens": 120},
        },
    }


def _think_body() -> dict:
    return {
        "choices": [
            {"message": {"content": "<thinking>thinking</thinking>\nI think cars are fine.", "role": "assistant"}}
        ],
        "usage": {
            "prompt_tokens": 150,
            "completion_tokens": 50,
            "prompt_tokens_details": {"cached_tokens": 120},
        },
    }


def _no_cache_body() -> dict:
    return {
        "choices": [{"message": {"content": "hello", "role": "assistant"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 10},
    }


def _empty_body() -> dict:
    return {
        "choices": [{"message": {"content": "", "role": "assistant"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 0},
    }


class TestHealth:
    def test_success(self) -> None:
        client = _make_client()
        with patch("httpx.get") as mock_get:
            mock_get.return_value = _make_get_response(200, {"default_model": "test"})
            result = client.health()
            assert result["default_model"] == "test"

    def test_failure(self) -> None:
        client = _make_client()
        with patch("httpx.get") as mock_get:
            mock_get.side_effect = httpx.ConnectError("fail")
            with pytest.raises(OmlxClientError, match="health check failed"):
                client.health()


class TestModels:
    def test_success(self) -> None:
        client = _make_client()
        with patch("httpx.get") as mock_get:
            mock_get.return_value = _make_get_response(200, {"data": [{"id": "model1"}]})
            result = client.models()
            assert len(result) == 1
            assert result[0]["id"] == "model1"

    def test_failure(self) -> None:
        client = _make_client()
        with patch("httpx.get") as mock_get:
            mock_get.side_effect = httpx.ConnectError("fail")
            with pytest.raises(OmlxClientError, match="models check failed"):
                client.models()


class TestChat:
    def test_success(self) -> None:
        client = _make_client()
        req = ChatRequest(
            model="test", system="sys", user="usr",
            temperature=0.8, max_tokens=300,
            frequency_penalty=0.0, presence_penalty=0.0,
        )
        with patch("httpx.post") as mock_post:
            mock_post.return_value = _make_response(200, _success_body())
            result = client.chat(req)
            assert result.content == "I think cars are fine."
            assert result.usage.cached_tokens == 120
            assert result.usage.prompt_tokens == 150
            assert result.latency_ms >= 0

    def test_think_block_stripped(self) -> None:
        client = _make_client()
        req = ChatRequest(
            model="test", system="sys", user="usr",
            temperature=0.8, max_tokens=300,
            frequency_penalty=0.0, presence_penalty=0.0,
        )
        with patch("httpx.post") as mock_post:
            mock_post.return_value = _make_response(200, _think_body())
            result = client.chat(req)
            assert "<thinking>" not in result.content
            assert "I think cars are fine." == result.content

    def test_no_cache_field(self) -> None:
        client = _make_client()
        req = ChatRequest(
            model="test", system="sys", user="usr",
            temperature=0.8, max_tokens=300,
            frequency_penalty=0.0, presence_penalty=0.0,
        )
        with patch("httpx.post") as mock_post:
            mock_post.return_value = _make_response(200, _no_cache_body())
            result = client.chat(req)
            assert result.usage.cached_tokens == 0

    def test_429_retries(self) -> None:
        client = _make_client()
        req = ChatRequest(
            model="test", system="sys", user="usr",
            temperature=0.8, max_tokens=300,
            frequency_penalty=0.0, presence_penalty=0.0,
        )
        calls: list[float] = []
        client = OmlxClient("http://localhost:8000/v1", sleep=calls.append)
        with patch("httpx.post") as mock_post:
            mock_post.side_effect = [
                _make_response(429),
                _make_response(429),
                _make_response(200, _success_body()),
            ]
            result = client.chat(req)
            assert result.content == "I think cars are fine."
            assert len(calls) == 2

    def test_500_retries(self) -> None:
        calls: list[float] = []
        client = OmlxClient("http://localhost:8000/v1", sleep=calls.append)
        req = ChatRequest(
            model="test", system="sys", user="usr",
            temperature=0.8, max_tokens=300,
            frequency_penalty=0.0, presence_penalty=0.0,
        )
        with patch("httpx.post") as mock_post:
            mock_post.side_effect = [
                _make_response(500),
                _make_response(500),
                _make_response(200, _success_body()),
            ]
            client.chat(req)
            assert len(calls) == 2

    def test_connect_error_retries(self) -> None:
        calls: list[float] = []
        client = OmlxClient("http://localhost:8000/v1", sleep=calls.append)
        req = ChatRequest(
            model="test", system="sys", user="usr",
            temperature=0.8, max_tokens=300,
            frequency_penalty=0.0, presence_penalty=0.0,
        )
        with patch("httpx.post") as mock_post:
            mock_post.side_effect = httpx.ConnectError("fail")
            with pytest.raises(TransientOmlxError):
                client.chat(req)
            assert len(calls) == 2

    def test_400_no_retry(self) -> None:
        client = _make_client()
        req = ChatRequest(
            model="test", system="sys", user="usr",
            temperature=0.8, max_tokens=300,
            frequency_penalty=0.0, presence_penalty=0.0,
        )
        with patch("httpx.post") as mock_post:
            mock_post.return_value = _make_response(400, {"error": "bad"})
            with pytest.raises(OmlxClientError):
                client.chat(req)

    def test_empty_content(self) -> None:
        client = _make_client()
        req = ChatRequest(
            model="test", system="sys", user="usr",
            temperature=0.8, max_tokens=300,
            frequency_penalty=0.0, presence_penalty=0.0,
        )
        with patch("httpx.post") as mock_post:
            mock_post.return_value = _make_response(200, _empty_body())
            result = client.chat(req)
            assert result.content == ""

    def test_thinking_default_true(self) -> None:
        req = ChatRequest(
            model="test", system="sys", user="usr",
            temperature=0.8, max_tokens=300,
            frequency_penalty=0.0, presence_penalty=0.0,
        )
        assert req.thinking is False

    def test_thinking_false(self) -> None:
        req = ChatRequest(
            model="test", system="sys", user="usr",
            temperature=0.8, max_tokens=300,
            frequency_penalty=0.0, presence_penalty=0.0,
            thinking=False,
        )
        assert req.thinking is False


class TestStripThinkTags:
    def test_clean(self) -> None:
        assert OmlxClient._strip_think_tags("hello") == "hello"

    def test_plain_tags(self) -> None:
        assert OmlxClient._strip_think_tags("<thinking>x</thinking>hello") == "hello"

    def test_markdown_tags(self) -> None:
        assert OmlxClient._strip_think_tags("```thinking\nx\n```\nhello") == "hello"

    def test_no_close(self) -> None:
        assert OmlxClient._strip_think_tags("<thinking>x") == ""

    def test_empty(self) -> None:
        assert OmlxClient._strip_think_tags("") == ""
