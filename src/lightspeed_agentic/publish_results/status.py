"""Build Result CR status dicts from schema-driven agent output.

Agent field shapes come from /input/output-schema — this module does not
validate or reshape them. It copies allowed keys per Result kind, wraps
lifecycle conditions, and sets failureReason when the agent or sandbox
reports failure.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

CONDITION_STARTED = "Started"
CONDITION_COMPLETED = "Completed"
REASON_STEP_STARTED = "StepStarted"
REASON_SUCCEEDED = "Succeeded"
REASON_FAILED = "Failed"

ACTION_REQUIRED_TRUE = "True"
ACTION_REQUIRED_FALSE = "False"

# Result kind → agent output keys copied into status (schema-owned shapes).
_STATUS_FIELDS_BY_KIND: dict[str, tuple[str, ...]] = {
    "AnalysisResult": ("options", "actionRequired", "diagnosis"),
    "ExecutionResult": ("actionsTaken",),
    "VerificationResult": ("checks", "summary"),
    "EscalationResult": ("summary", "content"),
}


def format_condition_time(when: datetime) -> str:
    """Format a timestamp for Kubernetes condition lastTransitionTime (RFC3339)."""
    if when.tzinfo is None:
        return when.isoformat() + "Z"
    return when.isoformat().replace("+00:00", "Z")


def action_required_value(value: bool) -> str:
    """Convert agent boolean actionRequired to CRD ActionRequiredValue."""
    return ACTION_REQUIRED_TRUE if value else ACTION_REQUIRED_FALSE


def build_conditions(
    *,
    started_at: datetime,
    completed_at: datetime,
    succeeded: bool,
) -> list[dict[str, Any]]:
    """Build Started + Completed conditions for a Result CR status."""
    completed_reason = REASON_SUCCEEDED if succeeded else REASON_FAILED
    return [
        {
            "type": CONDITION_STARTED,
            "status": "True",
            "reason": REASON_STEP_STARTED,
            "message": "Step started",
            "lastTransitionTime": format_condition_time(started_at),
        },
        {
            "type": CONDITION_COMPLETED,
            "status": "True",
            "reason": completed_reason,
            "message": "Step completed" if succeeded else "Step failed",
            "lastTransitionTime": format_condition_time(completed_at),
        },
    ]


def _infer_failure_reason(
    agent_output: dict[str, Any],
    failure_reason: str | None,
) -> str | None:
    """Resolve failureReason from explicit input or agent success=false."""
    if failure_reason is not None:
        return failure_reason
    if agent_output.get("success") is False:
        summary = agent_output.get("summary")
        if isinstance(summary, str) and summary:
            return summary
        return "Agent reported failure"
    return None


def _agent_succeeded(agent_output: dict[str, Any], failure_reason: str | None) -> bool:
    """Whether the agent run should be recorded as succeeded on the Result CR."""
    if failure_reason is not None:
        return False
    success = agent_output.get("success")
    if success is False:
        return False
    if success is True:
        return True
    # Analysis schema has no top-level success — absence means agent completed.
    return True


def _strip_empty_values(obj: Any) -> None:
    """Remove empty strings, lists, and dicts in-place so CRD constraints hold.

    Avoids violating minLength/minItems/minProperties on published status.
    LLMs often produce empty placeholders (e.g. ``"rootCause": ""``,
    ``"clusterScoped": []``) that are valid JSON but violate Kubernetes
    CRD validation rules.
    """
    if not isinstance(obj, dict):
        return
    for key in list(obj):
        val = obj[key]
        if isinstance(val, dict):
            _strip_empty_values(val)
            if not val:
                del obj[key]
        elif isinstance(val, list):
            for item in val:
                _strip_empty_values(item)
            if not val:
                del obj[key]
        elif isinstance(val, str) and val == "":
            del obj[key]


def build_status(
    kind: str,
    agent_output: dict[str, Any],
    *,
    failure_reason: str | None = None,
    started_at: datetime,
    completed_at: datetime,
) -> dict[str, Any]:
    """Assemble a Result CR status dict from agent output and lifecycle metadata.

    Parameters
    ----------
    kind:
        Result CR kind from result-template (e.g. AnalysisResult).
    agent_output:
        Parsed structured agent JSON (shape from /input/output-schema).
    failure_reason:
        Sandbox-level agent failure message (infra success, agent failed).
    started_at, completed_at:
        Wall-clock bounds for Started / Completed conditions.
    """
    fields = _STATUS_FIELDS_BY_KIND.get(kind)
    if fields is None:
        msg = f"unsupported Result kind: {kind!r}"
        raise ValueError(msg)

    resolved_failure = _infer_failure_reason(agent_output, failure_reason)
    succeeded = _agent_succeeded(agent_output, resolved_failure)

    status: dict[str, Any] = {}
    if resolved_failure is not None:
        status["failureReason"] = resolved_failure

    for key in fields:
        if key not in agent_output:
            continue
        value = agent_output[key]
        if key == "actionRequired" and isinstance(value, bool):
            value = action_required_value(value)
        status[key] = value

    _strip_empty_values(status)

    status["conditions"] = build_conditions(
        started_at=started_at,
        completed_at=completed_at,
        succeeded=succeeded,
    )
    return status
