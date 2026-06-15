"""Pydantic request/response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class RunRequest(BaseModel):
    """Operator POST body for ``POST /v1/agent/run``."""

    query: str
    systemPrompt: str | None = None
    outputSchema: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    timeout_ms: int | None = None


class RunMetrics(BaseModel):
    """Sandbox-owned telemetry for a single ``POST /run`` invocation."""

    model_config = ConfigDict(extra="forbid")

    latency_ms: int
    input_tokens: int
    output_tokens: int
    cost_usd: float | None = None
    model: str
    provider: str
    tool_calls_count: int


class RunResult(BaseModel):
    """Agent-owned outcome: envelope plus structured fields from ``outputSchema``."""

    model_config = ConfigDict(extra="allow")

    success: bool
    summary: str


class RunResponse(BaseModel):
    """HTTP envelope: ``metrics`` (sandbox) + ``result`` (agent)."""

    model_config = ConfigDict(extra="forbid")

    metrics: RunMetrics
    result: RunResult
