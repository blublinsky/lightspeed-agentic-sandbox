from __future__ import annotations

import logging

from lightspeed_agentic.logging import EventLogger
from lightspeed_agentic.types import (
    ContentBlockStopEvent,
    ResultEvent,
    ThinkingDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
)


def test_tool_call_logs_do_not_include_arguments(caplog) -> None:
    payload = "DO_NOT_LOG_TOOL_ARGUMENT"
    caplog.set_level(logging.INFO, logger="lightspeed_agentic")

    EventLogger("execution").log(ToolCallEvent(name="Bash", input=payload))

    assert "tool_use: Bash" in caplog.text
    assert payload not in caplog.text


def test_tool_result_logs_do_not_include_content(caplog) -> None:
    payload = "DO_NOT_LOG_TOOL_RESULT"
    caplog.set_level(logging.INFO, logger="lightspeed_agentic")

    EventLogger("execution").log(ToolResultEvent(output=payload))

    assert "[provider:execution] tool_result" in caplog.messages
    assert payload not in caplog.text


def test_thinking_log_split_preserves_boundary_whitespace(caplog) -> None:
    caplog.set_level(logging.INFO, logger="lightspeed_agentic")
    event_logger = EventLogger("run")
    reasoning = "a" * 1999 + " " + "b" * 10

    event_logger.log(ThinkingDeltaEvent(thinking=reasoning))
    event_logger.log(ResultEvent(text="Done"))

    parts = []
    for message in caplog.messages:
        for prefix in ("[provider:run] thinking: ", "[provider:run] thinking (cont.): "):
            if message.startswith(prefix):
                parts.append(message.removeprefix(prefix))
    assert "".join(parts) == reasoning


def test_thinking_log_marks_split_continuations_and_new_blocks(caplog) -> None:
    """Cap-split pieces carry a continuation marker; new blocks do not."""
    caplog.set_level(logging.INFO, logger="lightspeed_agentic")
    event_logger = EventLogger("run")

    event_logger.log(ThinkingDeltaEvent(thinking="a" * 2000))
    event_logger.log(ThinkingDeltaEvent(thinking="b" * 500))
    event_logger.log(ContentBlockStopEvent())
    event_logger.log(ThinkingDeltaEvent(thinking="new block"))
    event_logger.log(ResultEvent(text="Done"))

    thinking = [m for m in caplog.messages if m.startswith("[provider:run] thinking")]
    assert thinking[0].startswith("[provider:run] thinking: " + "a" * 10)
    assert thinking[1].startswith("[provider:run] thinking (cont.): " + "b" * 10)
    assert thinking[2] == "[provider:run] thinking: new block"


def test_event_logger_flush_emits_buffered_thinking(caplog) -> None:
    """Public flush is used on timeout/error exits."""
    caplog.set_level(logging.INFO, logger="lightspeed_agentic")
    event_logger = EventLogger("run")

    event_logger.log(ThinkingDeltaEvent(thinking="PARTIAL_REASONING"))
    event_logger.flush()

    assert "[provider:run] thinking: PARTIAL_REASONING" in caplog.messages


def test_long_tool_result_logs_no_content(caplog) -> None:
    payload = "DO_NOT_LOG_LONG_TOOL_RESULT" + "x" * 2_000
    caplog.set_level(logging.INFO, logger="lightspeed_agentic")

    EventLogger("execution").log(ToolResultEvent(output=payload))

    assert "[provider:execution] tool_result" in caplog.text
    assert "DO_NOT_LOG_LONG_TOOL_RESULT" not in caplog.text
    assert payload[-100:] not in caplog.text
