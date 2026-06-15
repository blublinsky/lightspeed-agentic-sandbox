"""Tests for FastAPI routes using mock providers."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from lightspeed_agentic.routes import build_router
from lightspeed_agentic.types import ProviderQueryOptions, ResultEvent, ToolCallEvent

from .conftest import MockProvider


def _result(data: dict) -> dict:
    return data["result"]


def _metrics(data: dict) -> dict:
    return data["metrics"]


def _assert_envelope(data: dict) -> None:
    assert set(data.keys()) == {"metrics", "result"}


def _make_app(provider) -> FastAPI:
    app = FastAPI()
    router = build_router(provider, skills_dir="/workspace", model="test-model")
    app.include_router(router, prefix="/v1/agent")
    return app


@pytest.mark.asyncio
async def test_run_endpoint():
    app = _make_app(MockProvider())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/agent/run",
            json={"query": "Diagnose the issue"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "metrics" in data
        assert "result" in data
        assert _result(data)["success"] is True
        assert "mock result" in _result(data)["summary"]
        assert _metrics(data)["model"] == "test-model"
        assert _metrics(data)["provider"] == "mock"
        assert _metrics(data)["input_tokens"] == 100
        assert _metrics(data)["output_tokens"] == 50
        assert _metrics(data)["cost_usd"] == 0.01
        assert _metrics(data)["tool_calls_count"] == 0
        assert _metrics(data)["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_run_with_system_prompt():
    app = _make_app(MockProvider())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/agent/run",
            json={
                "query": "Diagnose the issue",
                "systemPrompt": "You are an SRE agent.",
            },
        )
        assert resp.status_code == 200
        assert _result(resp.json())["success"] is True


@pytest.mark.asyncio
async def test_run_with_context():
    app = _make_app(MockProvider())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/agent/run",
            json={
                "query": "Diagnose the issue",
                "context": {
                    "targetNamespaces": ["default", "kube-system"],
                    "attempt": 2,
                    "previousAttempts": [{"attempt": 1, "failureReason": "timeout"}],
                },
            },
        )
        assert resp.status_code == 200
        assert _result(resp.json())["success"] is True


@pytest.mark.asyncio
async def test_run_with_output_schema():
    app = _make_app(MockProvider())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/agent/run",
            json={
                "query": "Diagnose",
                "outputSchema": {
                    "type": "object",
                    "properties": {"summary": {"type": "string"}},
                },
            },
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_run_with_timeout_applied():
    """Verify timeout_ms is actually used: a slow provider exceeds a 1ms timeout."""
    import asyncio

    class SlowProvider(MockProvider):
        async def query(self, _options):
            await asyncio.sleep(0.1)
            async for event in super().query(_options):
                yield event

    app = _make_app(SlowProvider())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/agent/run",
            json={"query": "test", "timeout_ms": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        _assert_envelope(data)
        assert _result(data)["success"] is False
        assert "timed out" in _result(data)["summary"].lower()
        assert _metrics(data)["latency_ms"] >= 1
        assert _metrics(data)["input_tokens"] == 0
        assert _metrics(data)["output_tokens"] == 0
        assert _metrics(data)["tool_calls_count"] == 0
        assert "cost_usd" not in _metrics(data)


@pytest.mark.asyncio
async def test_run_with_timeout_default():
    """Without timeout_ms the server default applies and the fast mock succeeds."""
    app = _make_app(MockProvider())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/agent/run",
            json={"query": "Diagnose"},
        )
        assert resp.status_code == 200
        assert _result(resp.json())["success"] is True


@pytest.mark.asyncio
async def test_run_empty_response():
    provider = MockProvider(events=[ResultEvent(text="")])
    app = _make_app(provider)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/agent/run", json={"query": "test"})
        assert resp.status_code == 200
        data = resp.json()
        _assert_envelope(data)
        assert _result(data)["success"] is False
        assert "empty" in _result(data)["summary"].lower()


@pytest.mark.asyncio
async def test_run_text_response():
    provider = MockProvider(events=[ResultEvent(text="Just plain text, not JSON")])
    app = _make_app(provider)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/agent/run", json={"query": "test"})
        data = resp.json()
        assert _result(data)["success"] is True
        assert _result(data)["summary"] == "Just plain text, not JSON"


@pytest.mark.asyncio
async def test_run_strips_metrics_from_model_json():
    """Model JSON must not leak a top-level metrics key into result."""
    provider = MockProvider(
        events=[
            ResultEvent(
                text=(
                    '{"success": true, "summary": "ok", '
                    '"metrics": {"latency_ms": 1}, "ticketId": "T-1"}'
                ),
            )
        ]
    )
    app = _make_app(provider)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/agent/run", json={"query": "test"})
        data = resp.json()
        assert _result(data)["ticketId"] == "T-1"
        assert "metrics" not in _result(data)
        assert _metrics(data)["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_run_omits_cost_usd_when_unknown():
    provider = MockProvider(
        events=[ResultEvent(text='{"success": true, "summary": "ok"}', cost_usd=0.0)]
    )
    app = _make_app(provider)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/agent/run", json={"query": "test"})
        data = resp.json()
        assert "cost_usd" not in data["metrics"]


@pytest.mark.asyncio
async def test_run_counts_tool_calls_before_result():
    provider = MockProvider(
        events=[
            ToolCallEvent(name="bash", input='{"cmd": "oc get pods"}'),
            ToolCallEvent(name="read", input='{"path": "/tmp/out"}'),
            ResultEvent(text='{"success": true, "summary": "ok"}'),
        ]
    )
    app = _make_app(provider)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/agent/run", json={"query": "test"})
        data = resp.json()
        _assert_envelope(data)
        assert _metrics(data)["tool_calls_count"] == 2


@pytest.mark.asyncio
async def test_run_agent_error_returns_envelope():
    class ErrorProvider(MockProvider):
        async def query(self, _options: ProviderQueryOptions) -> AsyncIterator:
            raise RuntimeError("boom")
            yield  # pragma: no cover — makes this an async generator

    app = _make_app(ErrorProvider())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/agent/run", json={"query": "test"})
        assert resp.status_code == 200
        data = resp.json()
        _assert_envelope(data)
        assert _result(data)["success"] is False
        assert "agent error" in _result(data)["summary"].lower()
        assert "boom" in _result(data)["summary"]


@pytest.mark.asyncio
async def test_run_agent_error_includes_partial_tool_call_metrics():
    class ErrorAfterToolCallProvider(MockProvider):
        async def query(self, _options: ProviderQueryOptions) -> AsyncIterator:
            yield ToolCallEvent(name="bash", input="{}")
            raise RuntimeError("boom")

    app = _make_app(ErrorAfterToolCallProvider())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/agent/run", json={"query": "test"})
        data = resp.json()
        _assert_envelope(data)
        assert _result(data)["success"] is False
        assert _metrics(data)["tool_calls_count"] == 1


@pytest.mark.asyncio
async def test_run_structured_fields_only_on_result():
    provider = MockProvider(
        events=[ResultEvent(text='{"success": true, "summary": "ok", "ticketId": "T-1"}')]
    )
    app = _make_app(provider)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/agent/run", json={"query": "test"})
        data = resp.json()
        _assert_envelope(data)
        assert _result(data)["ticketId"] == "T-1"
        assert "ticketId" not in data
