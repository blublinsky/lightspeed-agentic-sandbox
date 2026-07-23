# System Overview

The lightspeed-agentic-sandbox is a multi-provider agent runtime that runs inside ephemeral Kubernetes pods. It exposes a single HTTP endpoint (`POST /v1/agent/run`) consumed by the OpenShift Lightspeed operator. The runtime wraps DeepAgents (for Anthropic/Claude models), Gemini, and OpenAI LLM provider SDKs behind a unified provider abstraction and returns structured JSON responses.

## Behavioral Rules

### System Role

1. The sandbox is a stateless, one-shot worker. Each pod processes a single agent query and is disposable. No session state persists between requests.

2. The operator is the sole consumer of the sandbox HTTP API. The sandbox does not interpret workflow semantics (phases, retries, step ordering) — that logic belongs to the operator.

3. The sandbox delegates all tool execution, command invocation, and skill discovery to the underlying provider SDK. It does not implement custom tool executors.

### Component Inventory

4. The system has these major components: HTTP API layer (routes, models), provider abstraction (factory, query options, event model), provider adapters (DeepAgents, Gemini, OpenAI), configuration mapping (`config.py`), MCP resolution (`mcp.py`), health probes, and observability (`audit.py`, `metrics.py`, `tracing.py`).

5. Component behavioral rules: `run-api.md`, `provider-contract.md`, `configuration.md`, `health-probes.md`, `audit-logging.md`, `e2e-testing.md`.

### Lifecycle

6. At startup, the process runs `resolve_sdk()` / reasoning config parse, constructs a provider via the factory, builds the API router, registers health and metrics routes, initializes tracing in the app lifespan, and serves on port 8080.

7. The provider is selected once at startup via `LIGHTSPEED_PROVIDER` and cannot change during the process lifetime.

8. Model resolution uses canonical `LIGHTSPEED_MODEL` (mapped to SDK-specific model env vars), with package default fallback.

### Integration Boundaries

9. **Operator -> Sandbox:** HTTP POST with `RunRequest` JSON. The operator carries step semantics via `query`, `outputSchema`, and `context`. The sandbox returns `RunResponse` JSON.

10. **Sandbox -> Provider SDK:** The sandbox passes `ProviderQueryOptions` into the selected adapter and consumes an async event stream until a terminal `result` event.

11. **Provider SDK -> External:** Each SDK manages its own API authentication, tool execution, and skill discovery. The sandbox supplies credentials via environment variables but does not mediate API calls.

## Configuration Surface

| Field/Flag | Type | Default | Description |
|---|---|---|---|
| `LIGHTSPEED_PROVIDER` | string | `anthropic` | Selects the provider backend (resolves to `deepagents`, `gemini`, or `openai` SDK) |
| `LIGHTSPEED_SKILLS_DIR` | string | `/app/skills` | Skill root and provider working directory |
| `LIGHTSPEED_MODEL` | string | `claude-opus-4-6` | Canonical model identifier (mapped to SDK-specific env vars per provider) |

See `configuration.md` for the full environment variable reference.

## Constraints

- The sandbox is not a general-purpose API server. It serves one operator, one endpoint, one provider per pod.
- Provider SDK packages are optional Python extras. Only the selected provider's SDK needs to be installed, though the container image ships all three.
- The sandbox must remain deployable without network access during build (Konflux hermetic builds).

## Planned Changes

| Ticket | Summary |
|---|---|
| OLS-2914 | Register deprecated route aliases (`/analyze`, `/execute`, `/verify`) or remove from product docs |
| OLS-3033 | Align operator-passed `allowedTools` and `llm` with provider options |
| OLS-3038–OLS-3043 | TLS, mTLS, and network policies for operator-to-sandbox traffic |
