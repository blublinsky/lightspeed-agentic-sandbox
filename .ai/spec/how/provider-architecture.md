# Architecture: data flow, SDK integration

Audience: AI agents. File paths and symbols allowed here.
Package tree: `AGENTS.md`. Behavioral rules: `what/run-api.md`, `what/provider-contract.md`, `what/configuration.md`, `what/audit-logging.md`.

## Data Flow

1. Startup: `config.resolve_sdk()` maps `LIGHTSPEED_*` → SDK env; `parse_reasoning_config()`; `create_provider(sdk.name)`; `build_router(...)`; register health + metrics; lifespan initializes tracer.
2. Client (operator) `POST /v1/agent/run` with JSON body and optional `traceparent` / `x-agenticrun-uid`.
3. FastAPI validates `RunRequest`; `run_endpoint` computes timeout, system prompt, optional context prefix + query; may resolve MCP servers via `mcp.parse_mcp_servers()`.
4. Handler calls `provider.query(ProviderQueryOptions(...))` with model, turns, budget, tools, cwd, schema, reasoning_config, and resolved MCP server configs.
5. Handler async-iterates events; `EventLogger` and `AuditLogger` side effects; metrics updated; stops at first `result` event.
6. Handler parses `result.text` as JSON object or falls back to plain summary; returns `RunResponse`.

## Key Abstractions

- **Config mapping:** `resolve_sdk()` owns env → SDK name; factory does not read provider env vars.
- **Factory:** `create_provider(name)` lazy-imports the selected adapter.
- **Events:** Normalized `ProviderEvent` union decouples route layer from vendor streaming models.
- **Options:** `ProviderQueryOptions` is the single bundle passed into every adapter (includes `mcp_servers`, `reasoning_config`).
- **Router builder:** Env-based model resolution and default router parameters.

## Integration Points

- **FastAPI / Uvicorn:** ASGI entry `lightspeed_agentic.app:app`.
- **deepagents (+ langchain-anthropic, langchain-google-vertexai, langchain-aws, langchain-mcp-adapters):** `create_deep_agent`, `LocalShellBackend`, `ChatAnthropic` / Vertex / Bedrock, MCP via `MultiServerMCPClient`.
- **google-adk / google.genai:** `Agent`, `Runner`, `InMemorySessionService`, `ExecuteBashTool`, `SkillToolset`. MCP via `McpToolset` + `StreamableHTTPConnectionParams`.
- **openai-agents (+ openai):** `SandboxAgent`, `Runner`, `UnixLocalSandboxClient`. MCP via `MCPServerStreamableHttp`.
- **OpenTelemetry / Prometheus:** `tracing.py` TracerProvider; `audit.py` GenAI spans/events; `metrics.py` `/metrics`.

## Implementation Notes

- **DeepAgents model routing:** `_resolve_model()` checks `CLAUDE_CODE_USE_VERTEX` and `CLAUDE_CODE_USE_BEDROCK`.
- **DeepAgents thinking:** From `AIMessage` content / content_blocks; yield `ThinkingDeltaEvent` then `ContentBlockStopEvent`.
- **DeepAgents streaming:** `astream(stream_mode="messages")`.
- **Gemini bash:** Monkey-patches `run_async` for confirmation and `bash -c` wrapping.
- **OpenAI init:** One-time verbose logging and tracing disable.
- **MCP Secret headers:** Read first file (sorted by name) under `/var/secrets/mcp/<secretName>/` — see `what/configuration.md` (current behavior; stricter path was an orphan promise).
- **Containerfile:** Multi-stage hermetic Python/RPM build; `oc`/`kubectl` from ose-cli stage; no ripgrep install; user `agent`; `catatonit`; Uvicorn on 8080.
- **Tests / evals:** HTTP clients target `POST /v1/agent/run` (see `tests/` and `evals/`).
