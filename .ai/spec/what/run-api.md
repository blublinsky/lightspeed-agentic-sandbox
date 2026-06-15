# Behavioral spec: HTTP run API

Audience: AI agents (Claude). Precision over narrative.

Cross-references: provider behavior and events → `provider-contract.md`. Env defaults and ports → `configuration.md`.

## Behavioral Rules

1. **Operator integration boundary.** The Kubernetes operator (workflow engine) invokes the sandbox over HTTP using `POST /v1/agent/run` with a JSON body matching `RunRequest`. The sandbox returns `RunResponse` JSON with top-level **`metrics`** (sandbox telemetry) and **`result`** (agent output). The operator reads `metrics` for per-step observability and unmarshals **`result`** for workflow fields (`success`, `summary`, and structured keys from `outputSchema`). Step semantics arrive primarily via `query`, `outputSchema`, and `context`. The operator sends `systemPrompt` as empty; the sandbox applies a default persona when `systemPrompt` is empty or omitted (see rule 5). The sandbox does not interpret workflow phase names.

2. **Route mounting.** Agent routes are mounted under the path prefix `/v1/agent` on the FastAPI application. Probe routes (`/health`, `/ready`) are **not** under that prefix.

3. **Canonical run endpoint.** `POST /v1/agent/run` accepts `RunRequest` and returns `RunResponse`.

4. **RunRequest — `query` (required).** User task text. When `context` is present, the handler prepends a formatted context block to this text before sending the combined string to the provider (see rules 12–16).

5. **RunRequest — `systemPrompt`.** Optional. When omitted or null, the handler substitutes a fixed default assistant persona string.

6. **RunRequest — `outputSchema`.** Optional JSON-object schema. When present, forwarded to the provider as structured-output hints (see `provider-contract.md`). Schema properties describe fields inside the response **`result`** object (rules 20–22), not the HTTP envelope. The HTTP response still follows `RunResponse` shaping rules (rules 18–25).

7. **RunRequest — `context`.** Optional object. When present, must be formatted by the rules in 12–16; unknown keys are ignored if not read by the formatter.

8. **RunRequest — `timeout_ms`.** Optional. When set, caps wall-clock time for consuming the provider event stream until the first `result` event. When omitted, a router-level default timeout applies (see `configuration.md`).

9. **Per-run spend ceiling.** The route passes a fixed USD budget cap into provider options. This cap is **not** configurable via `RunRequest`.

10. **GET /health.** Returns a JSON object `{ "status": "ok" }` when the process is up (not mounted under `/v1/agent`).

11. **GET /ready.** Readiness probe (not under `/v1/agent`). Returns HTTP 200 with `{ "status": "ok" }` when all checks pass; HTTP 503 with `{ "status": "error", "checks": { ... } }` when any check fails. Checks and semantics: `health-probes.md`.

12. **Context prefix — envelope.** When `context` is non-empty, the formatter produces a block that starts with a fixed marker line, ends with a closing marker line, and is prepended to `query` with separating newlines.

13. **Context — `targetNamespaces`.** When present and non-empty (list), include a line listing target namespaces as a comma-separated join.

14. **Context — `attempt`.** When present (any), include a line labeling the attempt with placeholder text for the maximum (literal substring `of max` in the line; the formatter does not inject the max value).

15. **Context — `previousAttempts`.** When present and non-empty (iterable of objects), include a header line then one bullet line per entry with attempt index and optional `failureReason`.

16. **Context — `approvedOption`.** When present and non-empty (object), append a bounded block: title, diagnosis root cause, proposal description, risk, reversibility, and optional action list with type and description; surround with explicit “approved remediation” and “do not exceed listed actions” banners.

17. **Stream consumption.** The handler iterates the provider async iterator until a `result` event; earlier events are logged but do not terminate the request. See `provider-contract.md` for event types.

18. **RunResponse — envelope.** Every response is a JSON object with exactly two top-level keys: **`metrics`** (object, sandbox-owned) and **`result`** (object, agent-owned). Both MUST be present on success, timeout, agent error, and empty-result paths. HTTP status remains 200 for handler-level outcomes (rules 23–25); transport failures are out of scope here.

19. **RunResponse — `metrics`.** Sandbox-computed telemetry for the `/run` invocation. Fields:

    | Field | Type | Required | Notes |
    |-------|------|----------|-------|
    | `latency_ms` | integer | yes | Wall-clock milliseconds for the handler (including provider stream wait). |
    | `input_tokens` | integer | yes | Sum from provider `result` event when available; else `0`. |
    | `output_tokens` | integer | yes | Sum from provider `result` event when available; else `0`. |
    | `cost_usd` | number or null | no | USD when the provider reports it (Claude SDK path). Omitted or `null` when unknown — MUST NOT be `0` as a stand-in for unknown. |
    | `model` | string | yes | Model id used for the run (router-resolved). |
    | `provider` | string | yes | Provider adapter name (`claude`, `gemini`, `openai`, …). |
    | `tool_calls_count` | integer | yes | Count of provider `tool_call` events observed before the terminal `result` event. |

    Callers MUST treat `metrics` as authoritative for telemetry; it is not derived from model JSON.

20. **RunResponse — `result` core fields.** Every **`result`** object includes `success` (boolean) and `summary` (string). Additional keys are allowed on **`result`** when structured output applies (rule 21).

21. **Structured agent output.** When the final provider `result` event text parses as a JSON object, the handler builds **`result`** with `success` from that object’s `success` key defaulting to true when absent, `summary` from `summary` defaulting to the raw result text when absent, and merges remaining keys as extra fields on **`result`** (not at the HTTP top level).

22. **Text fallback.** When the final provider `result` text is not a JSON object (parse failure or non-object JSON), **`result`** contains only `success=true` and `summary` equal to the full result text.

23. **Timeout.** When waiting for the provider exceeds the effective timeout, **`result.success`** is false and **`result.summary`** states timeout and includes the timeout duration in milliseconds. **`metrics`** reflects elapsed wall-clock time up to the timeout.

24. **Agent errors.** On any other exception during the provider call, **`result.success`** is false and **`result.summary`** is prefixed with a fixed agent-error label and the exception message. **`metrics`** reflects partial observation when available.

25. **Empty result.** When the stream ends without non-empty final provider `result` text, **`result.success`** is false with a fixed empty-response summary.

26. **Allowed tools.** The route passes the default allowed-tools list into provider options; callers cannot override via `RunRequest` (see `provider-contract.md`).

### Example responses

Structured success:

```json
{
  "metrics": {
    "latency_ms": 8420,
    "input_tokens": 1200,
    "output_tokens": 340,
    "cost_usd": 0.0042,
    "model": "claude-opus-4-6",
    "provider": "claude",
    "tool_calls_count": 3
  },
  "result": {
    "success": true,
    "summary": "Found root cause",
    "options": []
  }
}
```

Timeout (envelope-only live check; no assertion on free-text summary in BDD):

```json
{
  "metrics": {
    "latency_ms": 1,
    "input_tokens": 0,
    "output_tokens": 0,
    "model": "gpt-5-mini",
    "provider": "openai",
    "tool_calls_count": 0
  },
  "result": {
    "success": false,
    "summary": "Agent timed out after 1ms"
  }
}
```

Unknown cost (Gemini/OpenAI adapters today):

```json
{
  "metrics": {
    "latency_ms": 5100,
    "input_tokens": 800,
    "output_tokens": 120,
    "model": "gemini-2.5-flash",
    "provider": "gemini",
    "tool_calls_count": 1
  },
  "result": {
    "success": true,
    "summary": "Done"
  }
}
```

(`cost_usd` omitted when not reported by the provider.)

## Configuration Surface

| Mechanism | Purpose |
|-----------|---------|
| `RunRequest.timeout_ms` | Per-request wall-clock limit for waiting on the first `result` event (milliseconds). |
| Router `default_timeout_ms` | Used when `timeout_ms` is omitted (see `configuration.md`). |
| `LIGHTSPEED_SKILLS_DIR` | Working directory / skill root forwarded as provider `cwd` (see `configuration.md`). |

## Constraints

- The handler does not expose `max_turns`, model id, provider id, or tool allowlists on `RunRequest`; those are fixed or environment-driven per `configuration.md` and router construction.
- Streaming to the HTTP client is out of scope for `POST /run`; provider streaming may be used internally only if the adapter enables it (see `how/provider-architecture.md`).

## Planned Changes

- Operator payload may later include `llm` and `allowedTools` per target architecture docs; sandbox route does not read them today. [PLANNED: OLS-3033]
- TLS, network policy, and ingress hardening for the sandbox service. [PLANNED: OLS-3038–OLS-3043]
- Per-step metrics persistence on operator CRD status and export schema alignment. [PLANNED: OLS-3130 — operator consumes `metrics` separately from `result`]

## Verification

1. **Unit tests** (`tests/test_routes.py`) — mocked provider: `metrics`/`result` envelope, timeout, empty result, text fallback, structured field merge (rules 18–25).
2. **Container BDD** (`tests/e2e/features/structured_output.feature`, `skills.feature`) — live `/run` validates structured fields under **`result`**.

| Artifact | Rules exercised | Notes |
|----------|-----------------|-------|
| [structured_output.feature](../../../tests/e2e/features/structured_output.feature) | 3, 6, 18–22 | Structured output and text fallback under **`result`** |
| [skills.feature](../../../tests/e2e/features/skills.feature) | 3, 18–22 | `/run` success paths with skills mounted |
| [test_routes.py](../../../tests/test_routes.py) | 3, 5, 6, 8, 18–25 | Mocked provider: envelope, timeout, empty result, cost omission |
