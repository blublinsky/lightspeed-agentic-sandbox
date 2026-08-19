# Behavioral spec: Batch entrypoint

Audience: AI agents (Claude). Precision over narrative.

Cross-references: provider behavior and events → `provider-contract.md`. Env defaults → `configuration.md`. Result CR publishing → `publish_results/` in `how/project-structure.md`.

The sandbox runs as a one-shot batch process (OLS-3066). There is **no HTTP server** — no FastAPI routes, no `/health` or `/ready` probes, no inbound connections.

## Behavioral Rules

### Integration and lifecycle

1. **Operator integration boundary.** The operator mounts a ConfigMap at `/input/` and starts the sandbox container. The process reads files, runs the LLM agent, publishes a Result CR, and exits. The sandbox does not interpret workflow phase names — the operator carries step semantics via input files and `context`.

2. **No HTTP server.** The sandbox MUST NOT start a FastAPI/HTTP server. The process reads files, runs the agent, writes results, and exits.

3. **Process entry.** The container runs `python -m lightspeed_agentic.batch` (via `catatonit` as PID 1). See `configuration.md` rule 14.

### Input files (`/input/`)

4. **Required files.** The operator mounts a read-only ConfigMap at `/input/` with keys mapped to files:
   - `/input/query` — step input text (must not embed role/system instructions after OLS-3491)
   - `/input/output-schema` — JSON schema for structured agent output
   - `/input/context` — JSON object (`targetNamespaces`, `previousAttempts`, `approvedOption`, `executionResult`, …)
   - `/input/result-template` — pre-filled Result CR JSON (`apiVersion`, `kind`, `metadata`, `spec`); sandbox fills `status` only

5. **Optional system prompt.** `/input/system-prompt` — step system instructions. When the file is **absent** or empty, the sandbox uses the fixed default persona (`"You are an AI agent."`). Absence of this file is valid and MUST NOT be treated as an input-read failure (contrast rule 15).

6. **Input read failures.** When a required file cannot be read or JSON is invalid, the sandbox MUST treat this as a sandbox failure (rule 23).

### Agent execution

7. **Provider startup.** The batch entrypoint calls `resolve_sdk()`, `parse_reasoning_config()`, and `parse_mcp_servers()` before any OTLP export or readiness I/O, then `run_readiness_checks()` (see `health-probes.md`), `init_tracer()`, `create_provider()`, and `resolve_router_model()` once per run. When readiness checks fail, the sandbox MUST fail before invoking the LLM (sandbox failure path, rule 23). Provider selection cannot change mid-process.

8. **Agent query.** The sandbox runs `run_agent_query()` with system prompt, query, output schema, context, skills directory, model, MCP servers, and reasoning config. Tool execution (kubectl, oc) is unchanged — delegated to provider SDKs.

9. **Per-run timeout.** Wall-clock limit for the provider event stream defaults to 300_000 ms. Override via `LIGHTSPEED_TIMEOUT_MS` (milliseconds). On timeout, agent output is `success=false` with a timed-out summary (same semantics as former HTTP rule 21).

10. **Per-run spend ceiling.** A fixed USD budget cap is passed into provider options; not configurable via input files.

11. **Allowed tools.** The default allowed-tools list is passed into provider options; callers cannot override via input files (see `provider-contract.md`).

### Context prefix formatting

When `context` is non-empty, `format_context_prefix()` prepends a block to `query` before the provider call:

12. **Envelope.** Block starts with `[context]` and ends with `[/context]`, separated from query by newlines.

13. **`targetNamespaces`.** When present and non-empty, include a comma-separated namespace list.

14. **`attempt`.** When present, include `Attempt: {n} of max` (literal `of max`; max not injected).

15. **`previousAttempts`.** When present and non-empty, list each attempt with optional `failureReason`.

16. **`approvedOption`.** When present, include title, diagnosis root cause, remediation plan description, reversible flag, and optional actions (command, type, description) within approved-remediation banners. When `approvedOption` or other expanded fields are present but malformed, `format_context_prefix()` MUST fail with a clear `Invalid context: …` message; `run_agent_query()` returns `success=false` with that summary (agent failure path, rule 22) and MUST NOT invoke the LLM.

### Agent output shaping

The agent returns structured JSON via `run_agent_query()` (formerly HTTP `RunResponse` shaping):

17. **Structured JSON.** When final `result` text parses as a JSON object, `success` defaults to true when absent; `summary` defaults to raw text when absent; remaining keys are merged into the agent output dict.

18. **Text fallback.** Non-object JSON or parse failure → `success=true`, `summary` = full result text.

19. **Agent errors.** Provider exceptions → `success=false`, summary prefixed with agent-error label.

20. **Empty result.** No non-empty final `result` text → `success=false`, fixed empty-response summary.

### Result CR publishing

21. **Success path.** On sandbox success (agent completed, including agent failure), the sandbox MUST:
   - (a) merge agent structured output into Result CR `status` fields per step kind (`publish_results/status.py`),
   - (b) set `status.conditions` with `Started=True` and `Completed=True` (`Started.lastTransitionTime` = wall clock immediately before `run_agent_query()`; `Completed` = after agent returns),
   - (c) create the CR from `result-template` (metadata + spec) via the Kubernetes API,
   - (d) update the CR `status` subresource via the Kubernetes API,
   - (e) exit 0.

22. **Agent failure path.** When agent output has `success=false` or rule 19–20 applies, the sandbox MUST still publish the Result CR with `status.failureReason` set from the agent summary, `Completed=True` with `reason=Failed` when applicable (`publish_results/status.py`), and **exit 0**. Exit 0 means the **sandbox process** completed its job (read input, ran agent, published Result CR); it does **not** mean the agent step succeeded.

    The operator treats `PodSucceeded` (exit 0) as the signal to read the Result CR, then `validateResultCR` in `lightspeed-agentic-operator/controller/agenticrun/pod_handler.go` checks `status.failureReason` and `Completed.reason=Failed`. When either indicates agent failure, the operator sets the step condition to `False` with `ReasonSandboxFailed` and the CR message — **not** `ReasonSucceeded`. See operator `sandbox-execution.md` rule 8. Exit non-zero on this path would make `PodFailed`; the operator would use the termination log / exit code (rule 43e) and would **not** consume `failureReason` from the Result CR.

23. **Sandbox failure path.** When input cannot be read, readiness checks fail, Kubernetes create/update fails, or any other infrastructure error occurs, the sandbox MUST write a human-readable message to `/dev/termination-log` (max 4096 bytes) and exit non-zero. The operator reads `pod.status.containerStatuses[].state.terminated.message` — **no Result CR is published** on this path (contrast rules 21–22).

24. **Kubernetes API (not `oc`).** Publishing uses the `kubernetes` Python client (`CustomObjectsApi`): `create_namespaced_custom_object` for create (HTTP 409 AlreadyExists tolerated for idempotent retry), then `replace_namespaced_custom_object_status` for status. In a Kubernetes pod (`KUBERNETES_SERVICE_HOST` set), authentication MUST use in-cluster config only; if that fails, the sandbox MUST fail publish (sandbox failure path, rule 23) and MUST NOT fall back to a local kubeconfig file. Outside a cluster (local dev), `kubeconfig` MAY be used when in-cluster config is unavailable. The sandbox MUST NOT shell out to `oc` for Result CR lifecycle.

25. **RBAC.** The sandbox ServiceAccount MUST have `create` and `update` (with `status` subresource) on `AnalysisResult`, `ExecutionResult`, `VerificationResult`, and `EscalationResult` in the AgenticRun namespace.

### Observability

26. **Tracing.** When `LIGHTSPEED_AUDIT_ENABLED=true` or `OTEL_EXPORTER_OTLP_ENDPOINT` is set, `batch.main()` calls `init_tracer()` / `shutdown_tracer()` around the agent run. When both are unset, OTEL providers are not initialized (no exporters, no `LoggingHandler`). `LIGHTSPEED_AGENTICRUN_UID` and `LIGHTSPEED_AGENTICRUN_STEP` stamp spans and bridged OTLP logs when OTEL is active (see `audit-logging.md`). When the operator sets W3C `TRACEPARENT` on the pod, `batch.main()` passes it to `run_agent_query()` so the inference span is a child of the operator phase span. When `TRACEPARENT` is unset, the sandbox generates a new trace ID (graceful degradation).

27. **Metrics.** Prometheus histograms (`metrics.py`) are recorded in-process during `run_agent_query()` for unit-test verification. The batch entrypoint MUST NOT expose `/metrics` and MUST NOT push or export histograms at shutdown (one-shot pods; use OTLP traces for operational token/duration signals — see `audit-logging.md` rule 19).

## Configuration Surface

| Mechanism | Purpose |
|-----------|---------|
| `LIGHTSPEED_TIMEOUT_MS` | Per-run agent timeout (milliseconds); default 300_000 |
| `LIGHTSPEED_SKILLS_DIR` | Skills root and provider `cwd` (default `/app/skills`) |
| `resolve_router_model()` | Model from `LIGHTSPEED_MODEL` → SDK env → package default |
| Input files under `/input/` | Query, schema, context, template, optional system prompt |

## Constraints

- `max_turns`, model id, provider id, and tool allowlists are not in input files; fixed or env-driven per `configuration.md`.
- Provider streaming is internal only; no streaming to an HTTP client.

## Planned Changes

- Operator may later pass `llm` and `allowedTools` via input or env. [PLANNED: OLS-3033]
- `system-prompt` file as sole system-instructions carrier. [PLANNED: OLS-3491]

## Verification

Harness scope: [e2e-testing.md](e2e-testing.md). **Note:** container BDD scenarios still target the removed HTTP API; batch behavior is verified in unit tests until the harness is migrated.

| Artifact | Rules exercised | Notes |
|----------|-----------------|-------|
| [test_batch_input.py](../../../tests/test_batch_input.py) | 4–6 | Required/optional `/input` files |
| [test_batch.py](../../../tests/test_batch.py) | 2, 7, 15, 21–23 | Entrypoint orchestration including readiness fail-fast (mocked) |
| [test_run_agent.py](../../../tests/test_run_agent.py) | 8–20 | Agent query, context prefix, timeouts |
| [test_ready.py](../../../tests/test_ready.py) | 7 | R1 readiness checks (`health-probes.md`) |
| [test_publish_results_publish.py](../../../tests/test_publish_results_publish.py) | 21, 24 | K8s create + status replace |
| [test_publish_results_status.py](../../../tests/test_publish_results_status.py) | 21 | Status assembly from agent output |
| [test_model_resolution.py](../../../tests/test_model_resolution.py) | 7 | Model env resolution |

Legacy HTTP BDD ([sandbox_e2e.feature](../../../tests/e2e/features/sandbox_e2e.feature), etc.) and evals HTTP clients are **out of date** with the batch entrypoint.
