"""Tests for Result CR status assembly."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lightspeed_agentic.publish_results.status import (
    _MAX_LEN_DIAGNOSIS_ROOT_CAUSE,
    _MAX_LEN_DIAGNOSIS_SUMMARY,
    _MAX_LEN_OPTION_SUMMARY,
    _MAX_LEN_OPTION_TITLE,
    _MAX_LEN_PLAN_DESCRIPTION,
    ACTION_REQUIRED_FALSE,
    ACTION_REQUIRED_TRUE,
    _sanitize_analysis_options,
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


class TestSanitizeAnalysisOptions:
    def test_truncates_option_title(self) -> None:
        opt = {"title": "x" * 300, "summary": "s", "diagnosis": {"summary": "d", "rootCause": "r"}}
        result = _sanitize_analysis_options([opt])
        assert len(result[0]["title"]) == _MAX_LEN_OPTION_TITLE

    def test_truncates_option_summary(self) -> None:
        opt = {"title": "t", "summary": "x" * 2000, "diagnosis": {"summary": "d", "rootCause": "r"}}
        result = _sanitize_analysis_options([opt])
        assert len(result[0]["summary"]) == _MAX_LEN_OPTION_SUMMARY

    def test_truncates_diagnosis_fields(self) -> None:
        opt = {
            "title": "t",
            "diagnosis": {
                "summary": "x" * 10000,
                "rootCause": "y" * 2000,
            },
        }
        result = _sanitize_analysis_options([opt])
        assert len(result[0]["diagnosis"]["summary"]) == _MAX_LEN_DIAGNOSIS_SUMMARY
        assert len(result[0]["diagnosis"]["rootCause"]) == _MAX_LEN_DIAGNOSIS_ROOT_CAUSE

    def test_truncates_plan_description(self) -> None:
        opt = {
            "title": "t",
            "diagnosis": {"summary": "d", "rootCause": "r"},
            "remediationPlan": {
                "description": "x" * 10000,
                "actions": [{"type": "t", "description": "d"}],
            },
        }
        result = _sanitize_analysis_options([opt])
        assert len(result[0]["remediationPlan"]["description"]) == _MAX_LEN_PLAN_DESCRIPTION

    def test_zeros_diagnosis_when_summary_empty(self) -> None:
        actions = [{"type": "t", "description": "d"}]
        opt = {
            "title": "t",
            "diagnosis": {"summary": "", "rootCause": "cause"},
            "remediationPlan": {"description": "plan", "actions": actions},
        }
        result = _sanitize_analysis_options([opt])
        assert "diagnosis" not in result[0]
        assert "remediationPlan" not in result[0]

    def test_zeros_diagnosis_when_root_cause_empty(self) -> None:
        actions = [{"type": "t", "description": "d"}]
        opt = {
            "title": "t",
            "diagnosis": {"summary": "diag", "rootCause": ""},
            "remediationPlan": {"description": "plan", "actions": actions},
        }
        result = _sanitize_analysis_options([opt])
        assert "diagnosis" not in result[0]
        assert "remediationPlan" not in result[0]

    def test_zeros_diagnosis_when_summary_missing(self) -> None:
        actions = [{"type": "t", "description": "d"}]
        opt = {
            "title": "t",
            "diagnosis": {"rootCause": "cause"},
            "remediationPlan": {"description": "plan", "actions": actions},
        }
        result = _sanitize_analysis_options([opt])
        assert "diagnosis" not in result[0]
        assert "remediationPlan" not in result[0]

    def test_keeps_valid_diagnosis(self) -> None:
        actions = [{"type": "t", "description": "d"}]
        opt = {
            "title": "t",
            "diagnosis": {"summary": "diag", "rootCause": "cause"},
            "remediationPlan": {"description": "plan", "actions": actions},
        }
        result = _sanitize_analysis_options([opt])
        assert result[0]["diagnosis"]["summary"] == "diag"
        assert result[0]["diagnosis"]["rootCause"] == "cause"
        assert "remediationPlan" in result[0]

    def test_filters_non_dict_options(self) -> None:
        opts = [{"title": "t"}, "not-a-dict", 42, None]
        result = _sanitize_analysis_options(opts)
        assert len(result) == 1
        assert result[0]["title"] == "t"

    def test_removes_remediation_plan_when_diagnosis_missing(self) -> None:
        opt = {
            "title": "t",
            "remediationPlan": {"description": "plan", "actions": []},
        }
        result = _sanitize_analysis_options([opt])
        assert "remediationPlan" not in result[0]

    def test_removes_remediation_plan_when_diagnosis_not_dict(self) -> None:
        opt = {
            "title": "t",
            "diagnosis": "not-a-dict",
            "remediationPlan": {"description": "plan", "actions": []},
        }
        result = _sanitize_analysis_options([opt])
        assert "diagnosis" not in result[0]
        assert "remediationPlan" not in result[0]

    def test_null_actions_does_not_crash(self) -> None:
        opt = {
            "title": "t",
            "diagnosis": {"summary": "d", "rootCause": "r"},
            "remediationPlan": {"description": "p", "actions": None},
        }
        result = _sanitize_analysis_options([opt])
        assert result[0]["remediationPlan"]["description"] == "p"

    def test_null_steps_does_not_crash(self) -> None:
        opt = {
            "title": "t",
            "verification": {"description": "v", "steps": None},
        }
        result = _sanitize_analysis_options([opt])
        assert result[0]["verification"]["description"] == "v"

    def test_invalid_diagnosis_still_sanitizes_verification(self) -> None:
        opt = {
            "title": "t",
            "diagnosis": {"summary": "", "rootCause": "r"},
            "verification": {"description": "x" * 5000},
        }
        result = _sanitize_analysis_options([opt])
        assert "diagnosis" not in result[0]
        from lightspeed_agentic.publish_results.status import (
            _MAX_LEN_VERIFICATION_DESCRIPTION,
        )

        assert len(result[0]["verification"]["description"]) == _MAX_LEN_VERIFICATION_DESCRIPTION

    def test_build_status_calls_sanitize(self) -> None:
        agent = {
            "actionRequired": True,
            "options": [
                {
                    "title": "x" * 300,
                    "diagnosis": {"summary": "", "rootCause": "r"},
                },
            ],
        }
        status = build_status("AnalysisResult", agent, started_at=_dt(), completed_at=_dt())
        assert len(status["options"][0]["title"]) == _MAX_LEN_OPTION_TITLE
        assert "diagnosis" not in status["options"][0]


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
