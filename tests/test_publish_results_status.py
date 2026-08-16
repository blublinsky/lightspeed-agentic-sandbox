"""Tests for Result CR status assembly."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lightspeed_agentic.publish_results.status import (
    ACTION_REQUIRED_FALSE,
    ACTION_REQUIRED_TRUE,
    build_conditions,
    build_status,
    format_condition_time,
)


def _dt() -> datetime:
    return datetime(2026, 8, 15, 12, 30, 0, tzinfo=UTC)


class TestFormatConditionTime:
    def test_utc_z_suffix(self) -> None:
        assert format_condition_time(_dt()) == "2026-08-15T12:30:00Z"


class TestBuildConditions:
    def test_success_path(self) -> None:
        started = _dt()
        completed = datetime(2026, 8, 15, 12, 31, 0, tzinfo=UTC)
        conds = build_conditions(started_at=started, completed_at=completed, succeeded=True)
        assert len(conds) == 2
        assert conds[0]["type"] == "Started"
        assert conds[0]["reason"] == "StepStarted"
        assert conds[1]["type"] == "Completed"
        assert conds[1]["reason"] == "Succeeded"

    def test_failure_path(self) -> None:
        conds = build_conditions(started_at=_dt(), completed_at=_dt(), succeeded=False)
        assert conds[1]["reason"] == "Failed"


class TestBuildStatusAnalysis:
    def test_success_copies_schema_fields(self) -> None:
        agent = {
            "actionRequired": True,
            "options": [{"title": "fix"}],
            "diagnosis": {"summary": "s", "rootCause": "r"},
        }
        status = build_status(
            "AnalysisResult",
            agent,
            started_at=_dt(),
            completed_at=_dt(),
        )
        assert status["actionRequired"] == ACTION_REQUIRED_TRUE
        assert status["options"] == agent["options"]
        assert status["diagnosis"] == agent["diagnosis"]
        assert "failureReason" not in status
        assert status["conditions"][1]["reason"] == "Succeeded"

    def test_action_required_false(self) -> None:
        agent = {
            "actionRequired": False,
            "options": [],
            "diagnosis": {"summary": "s", "rootCause": "r"},
        }
        status = build_status("AnalysisResult", agent, started_at=_dt(), completed_at=_dt())
        assert status["actionRequired"] == ACTION_REQUIRED_FALSE


class TestBuildStatusExecution:
    def test_success(self) -> None:
        agent = {
            "success": True,
            "actionsTaken": [{"type": "patch", "description": "d", "outcome": "Succeeded"}],
        }
        status = build_status("ExecutionResult", agent, started_at=_dt(), completed_at=_dt())
        assert status["actionsTaken"] == agent["actionsTaken"]
        assert status["conditions"][1]["reason"] == "Succeeded"

    def test_agent_failure_from_success_false(self) -> None:
        agent = {"success": False, "summary": "patch failed", "actionsTaken": []}
        status = build_status("ExecutionResult", agent, started_at=_dt(), completed_at=_dt())
        assert status["failureReason"] == "patch failed"
        assert status["conditions"][1]["reason"] == "Failed"


class TestBuildStatusVerification:
    def test_copies_checks_and_summary(self) -> None:
        agent = {
            "success": True,
            "checks": [{"name": "c", "result": "Passed", "source": "cmd", "value": "ok"}],
            "summary": "all good",
        }
        status = build_status("VerificationResult", agent, started_at=_dt(), completed_at=_dt())
        assert status["checks"] == agent["checks"]
        assert status["summary"] == "all good"


class TestBuildStatusEscalation:
    def test_copies_summary_and_content(self) -> None:
        agent = {"success": True, "summary": "esc", "content": "details"}
        status = build_status("EscalationResult", agent, started_at=_dt(), completed_at=_dt())
        assert status["summary"] == "esc"
        assert status["content"] == "details"


class TestBuildStatusFailureReason:
    def test_explicit_failure_reason(self) -> None:
        status = build_status(
            "ExecutionResult",
            {"success": True, "actionsTaken": []},
            failure_reason="LLM timeout",
            started_at=_dt(),
            completed_at=_dt(),
        )
        assert status["failureReason"] == "LLM timeout"
        assert status["conditions"][1]["reason"] == "Failed"

    def test_unknown_kind_raises(self) -> None:
        with pytest.raises(ValueError, match="unsupported Result kind"):
            build_status("UnknownResult", {}, started_at=_dt(), completed_at=_dt())
