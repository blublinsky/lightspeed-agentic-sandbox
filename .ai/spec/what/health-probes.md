# Behavioral spec: readiness checks

Audience: AI agents (Claude). Precision over narrative.

Cross-references: batch lifecycle → `run-api.md`. Credential env mapping → `configuration.md`.

> **HTTP probes superseded (OLS-3066).** There is no `GET /health` or `GET /ready`.
> Readiness runs in-process at batch startup before the LLM is invoked.

## Behavioral Rules

1. **Fail-fast before LLM.** After `resolve_sdk()`, `batch.main()` MUST call `run_readiness_checks(sdk)` before `create_provider()` or `run_agent_query()`. When any check fails, the sandbox MUST use the sandbox failure path (`run-api.md` rule 23): write a termination log with per-check status strings and exit non-zero.

2. **R1 — Credential env.** `check_provider_env(expected_envs, credential_file_envs)` — required env vars from `ResolvedSDK` MUST be set and non-empty. For env vars listed in `credential_file_envs` (Vertex: `GOOGLE_APPLICATION_CREDENTIALS`), the path MUST exist, be readable, and non-empty.

3. **No endpoint network probe.** The sandbox MUST NOT HTTP-probe provider base URLs before the agent run. Endpoint reachability is established when the provider SDK invokes the LLM API.

| Backend | Required env var(s) |
|---------|-------------------|
| `anthropic` (direct) | `ANTHROPIC_API_KEY` |
| `vertex/*` | `GOOGLE_APPLICATION_CREDENTIALS` (file path) |
| `openai` (direct) | `OPENAI_API_KEY` |
| `azure` | `AZURE_OPENAI_API_KEY` |
| `bedrock` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` |

4. **MCP reachability.** Not implemented; no Jira story.

## Verification

| Artifact | Rules exercised |
|----------|-----------------|
| [test_ready.py](../../../tests/test_ready.py) | R1, `run_readiness_checks()` |
| [test_batch.py](../../../tests/test_batch.py) | Rule 1 (fail-fast path) |

Container BDD probe scenarios in [sandbox_e2e.feature](../../../tests/e2e/features/sandbox_e2e.feature) target the **removed** HTTP API and are pending harness migration.
