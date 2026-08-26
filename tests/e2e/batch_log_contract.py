"""Batch pod log contract for E2E response enrichment.

Live batch Jobs run the published sandbox image. Result CR status on ``:main`` often
only exposes a generic ``summary`` (e.g. ``Step completed``). BDD assertions therefore
fall back to the agent's logged result line.

That line is emitted by ``EventLogger`` in ``lightspeed_agentic.logging``::

    logger.info("[provider:%s] output: %s", phase, event.text[:MAX_RESULT_LOG])

With ``phase="run"`` this becomes ``[provider:run] output: ...``. If this format
changes in the sandbox image, update ``PROVIDER_OUTPUT_LOG_PREFIX`` and the unit
tests in ``tests/test_batch_e2e_helpers.py`` before live BDD will fail loudly.
"""

from __future__ import annotations

PROVIDER_OUTPUT_LOG_PREFIX = "[provider:run] output: "

_GENERIC_CR_SUMMARIES = frozenset({"step completed", "step failed"})
