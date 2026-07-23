# Audit Logging

Implementation spec for compliance audit logging in the agentic sandbox. Parent spec: `ols/.ai/spec/what/audit-logging.md` (authoritative for cross-repo requirements, event semantics, correlation contract, and OTel GenAI attribute reference).

Telemetry aligns with [OTel GenAI Semantic Conventions](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/README.md) (v1.41).

## Behavioral Rules

### Span Naming and Kinds

1. The sandbox MUST create a `chat {gen_ai.request.model}` span (e.g., `chat claude-sonnet-4-20250514`) as a child of the operator's span (using the received trace context). This is the **inference span** covering the full SDK inference call. Span kind MUST be `CLIENT`.

2. The sandbox MUST create an `execute_tool {gen_ai.tool.name}` span (e.g., `execute_tool Bash`) for each tool call/result pair. These are children of the inference span. Span kind MUST be `INTERNAL`.

3. The sandbox does not run its own agent loop — it consumes events from the provider SDK's internal agentic loop. Spans are created alongside the existing event normalization in each provider adapter.

### GenAI Attributes — Inference Span

4. The inference span (`chat {gen_ai.request.model}`) MUST carry the following attributes:

| Attribute | Requirement | Description |
|---|---|---|
| `gen_ai.operation.name` | Required | `"chat"` |
| `gen_ai.request.model` | Required | Model name requested (e.g., `claude-sonnet-4-20250514`) |
| `gen_ai.response.model` | Recommended | Actual model from SDK response |
| `gen_ai.provider.name` | Required | Provider name (e.g., `anthropic`, `openai`, `google`) |
| `gen_ai.usage.input_tokens` | Recommended | Input token count for this operation |
| `gen_ai.usage.output_tokens` | Recommended | Output token count for this operation |
| `agenticrun.uid` | Required (custom) | AgenticRun CR metadata.uid as received (hyphens preserved) — cross-trace correlation key |
| `server.address` | Recommended | LLM API endpoint hostname |

5. `agenticrun.uid` MUST be received from the operator's context (via `traceparent` header propagation and/or as a request parameter on `/v1/agent/run`). The sandbox MUST propagate it as a span attribute on all spans.

### GenAI Attributes — Tool Span

6. Each tool execution span (`execute_tool {gen_ai.tool.name}`) MUST carry the following attributes:

| Attribute | Requirement | Description |
|---|---|---|
| `gen_ai.operation.name` | Required | `"execute_tool"` |
| `gen_ai.tool.name` | Required | Tool name (e.g., `Bash`, `ReadFile`) |
| `gen_ai.tool.call.id` | Recommended | Tool call ID from SDK |
| `gen_ai.tool.type` | Recommended | `"function"` |

### Span Events

7. The sandbox MUST emit `gen_ai.choice` span events attached to the inference span:
   - **Text output**: a `gen_ai.choice` event with a `gen_ai.completion` attribute containing the text content.
   - **Thinking/reasoning output**: a gen_ai.choice event with gen_ai.reasoning_content when the adapter emits thinking (DeepAgents, and Gemini/OpenAI when reasoning is configured per provider-contract.md). When the model emits both completion and thinking content, they MAY be combined into a single gen_ai.choice event with both attributes.

8. There are no separate `audit.agent.started` or `audit.agent.completed` events. The data previously captured by those events (phase, model, provider, success/failure, total tokens, total cost) MUST be recorded as span attributes on the inference span instead.

### Content Capture Policy

8a. The `gen_ai.completion` and `gen_ai.reasoning_content` span event attributes contain LLM output that may include PII or sensitive data. Recording these attributes MUST be opt-in, controlled by the audit content capture setting received from the operator. When content capture is disabled, `gen_ai.choice` events are still emitted but the content attributes are omitted. This aligns with the OTel GenAI semantic convention requirement level of Opt-In for content attributes.

### Trace Context Reception

9. The sandbox MUST extract the W3C `traceparent` header from incoming `/v1/agent/run` requests. The trace context from this header establishes the parent span for the inference span.

10. If no `traceparent` header is present, the sandbox MUST generate a new trace ID for the run (graceful degradation).

### Single-Emission Rule

11. Each audit-significant datum MUST be recorded exactly once as an OTel span or span event. Two exporters on the same TracerProvider produce two views of the same emission:
    - **OTLP exporter** sends spans to a trace backend (when endpoint configured).
    - **Stdout exporter** serializes the same span data as OTLP JSON to stdout (always, when audit enabled).

12. Python `logging` MUST emit only developer-debugging messages and MUST NOT re-emit data that appears in spans or span events. This collapses the current triple-emission (standard logging, JSON audit, OTEL span) into:
    - OTel spans/events for audit (two exporters, one emission).
    - Standard logging for developer debugging only (non-audit, non-structured).

### Structured Log Format

13. The stdout exporter MUST emit OTLP JSON — the OTel standard wire format. There is no custom JSON format. Both the stdout and OTLP exporters are destinations for the same TracerProvider spans.

14. The stdout exporter MUST NOT truncate span attributes or event attributes. Full fidelity is preserved. The stdout signal is the compliance record.

### Provider-Specific Instrumentation

15. **DeepAgents / Anthropic** (`providers/deepagents.py`): Emit `gen_ai.choice` span event with `gen_ai.completion` from `AIMessage` text content. Emit `gen_ai.choice` span event with `gen_ai.reasoning_content` from `AIMessage.content_blocks` entries with `type == "reasoning"`. Create `execute_tool {name}` spans from `AIMessage.tool_calls` and `ToolMessage` content. Set `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` from accumulated `usage_metadata`.

16. **OpenAI** (`providers/openai.py`): Emit `gen_ai.choice` with `gen_ai.completion` from stream text deltas (buffered). Emit `gen_ai.reasoning_content` from reasoning delta items when present. Create `execute_tool {name}` spans from tool call/output items. Set token usage from the stream end.

17. **Gemini** (`providers/gemini.py`): Emit `gen_ai.choice` with `gen_ai.completion` from text parts (buffered). Emit `gen_ai.reasoning_content` from thought parts when present. Create `execute_tool {name}` spans from function_call/response parts. Set token usage from the stream end.

### Metrics

18. The sandbox MUST expose a `/metrics` endpoint serving Prometheus metrics. The following `gen_ai.*` metrics MUST be implemented:

| Metric | Type | Unit | Labels |
|---|---|---|---|
| `gen_ai_client_token_usage` | Histogram | `{token}` | `gen_ai_token_type`, `gen_ai_request_model`, `gen_ai_provider_name`, `gen_ai_operation_name` |
| `gen_ai_client_operation_duration_seconds` | Histogram | `s` | `gen_ai_request_model`, `gen_ai_provider_name`, `gen_ai_operation_name` |
| `gen_ai_execute_tool_duration_seconds` | Histogram | `s` | `gen_ai_tool_name` |

19. Token usage histogram bucket boundaries MUST be `[1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864]` (per semconv recommendation). Reasoning tokens are tracked separately via `gen_ai.usage.reasoning_tokens` span attribute on inference spans, not as a `gen_ai.token.type` value.

### Configuration

20. The sandbox receives audit config from the operator via environment variables (`LIGHTSPEED_AUDIT_ENABLED`, `LIGHTSPEED_CAPTURE_CONTENT`, OTEL endpoint). When audit is disabled (`LIGHTSPEED_AUDIT_ENABLED` false/unset per implementation), the sandbox MUST NOT emit `gen_ai.choice` content events and MUST NOT use the stdout audit exporter path gated by that flag. Inference and tool spans may still be created for the request path (current code and unit tests). When audit is enabled, spans and span events emit per the rules above.

21. When an OTEL endpoint is configured (passed from operator), the sandbox MUST configure an OTLP exporter targeting that endpoint. When absent, a no-op OTLP exporter is used. The stdout exporter always emits OTLP JSON when audit is enabled.

### OTLP Log Emission (Templog) [PLANNED: OLS-3515]

22. [PLANNED: OLS-3515] When the OTLP log endpoint environment variable is set (wired by the lightspeed-operator when `spec.templog` is enabled), the sandbox MUST also emit audit span data as OTLP log records to that endpoint. This is in addition to the stdout and OTLP trace exporters.

23. [PLANNED: OLS-3515] Each OTLP log record MUST carry: `agenticrun.uid` as a log record attribute (raw Kubernetes `metadata.uid` with hyphens, via `x-agenticrun-uid`), `agenticrun.phase` (from `derive_phase()`), and the span event data as the log record body. TraceID carries the per-phase trace id from `traceparent`.

24. [PLANNED: OLS-3515] The OTLP log endpoint is independent of the OTEL tracing endpoint. Both can be active simultaneously.

25. [PLANNED: OLS-3515] When the OTLP log endpoint is absent, no OTLP log records are emitted. Graceful degradation.

### MCP Semantic Conventions [UNTRACKED]

26. MCP tool connectivity is implemented. Additional MCP span attributes (`mcp.method.name`, `mcp.session.id`, `mcp.protocol.version`, `network.transport`) are not implemented and have no Jira story. Do not treat this table as a current MUST until a ticket exists. Prefer `gen_ai.tool.*` on tool spans today.

## Cross-References

- `run-api.md` — `/v1/agent/run` endpoint where trace context arrives
- `provider-contract.md` — provider adapter event streams where spans and span events are created
- Parent workspace `ols/.ai/spec/what/templog.md` — Temporary audit log storage (cross-repo); sandbox emission tracked by OLS-3515
- `ols/.ai/spec/what/audit-logging.md` — parent spec (authoritative for correlation model, event semantics, OTel GenAI attribute reference)
- [OTel GenAI Semantic Conventions v1.41](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/README.md)
- [OTel MCP Semantic Conventions](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/mcp.md)
