# Project Structure

Package tree (authoritative for agents): see `AGENTS.md` Architecture section.
Do not maintain a duplicate path inventory here.

## Key Entry Points

| Entry point | How invoked |
|---|---|
| `lightspeed_agentic.app:app` | Uvicorn ASGI target (`uvicorn lightspeed_agentic.app:app --host 0.0.0.0 --port 8080`) |
| `config.resolve_sdk()` | Called once at startup in `app.py` before provider construction |
| `create_provider(sdk.name)` | Called once at module load in `app.py` with SDK name from `resolve_sdk()` |
| `build_router(provider, ...)` | Called once at module load in `app.py`, mounted at `/v1/agent` |
| `register_metrics_route(app)` | Registers `GET /metrics` on the FastAPI app |
| Lifespan `init_tracer` / `shutdown_tracer` | OTel TracerProvider setup/teardown in `app.py` |

## Naming Conventions

- **Package:** `lightspeed_agentic` under `src/` (hatchling src-layout).
- **Provider modules:** one file per provider in `providers/`, named after the SDK (`deepagents.py`, `gemini.py`, `openai.py`). Each exports a single `XProvider` class.
- **Route modules:** `routes/` contains `models.py` (Pydantic shapes), `query.py` (endpoint registration), `__init__.py` (router builder).
- **Observability modules:** `audit.py` (span events), `metrics.py` (`/metrics`), `tracing.py` (TracerProvider + traceparent).
- **Config / MCP:** `config.py` maps `LIGHTSPEED_*` → SDK env; `mcp.py` parses `LIGHTSPEED_MCP_SERVERS`.
- **Test layout:** `tests/` mirrors source structure. `tests/e2e/` holds BDD feature files and step definitions. `evals/` is a separate integration test suite run in containers.

## Dependency Organization

The project uses optional extras to gate provider SDKs:

| Extra | Packages |
|---|---|
| `deepagents` | `deepagents`, `langchain-anthropic`, `langchain-google-vertexai`, `langchain-aws`, `langchain-mcp-adapters` |
| `gemini` | `google-adk` |
| `openai` | `openai-agents` |
| `all` | All three provider extras |
| `dev` | All providers + test/lint tools |
| `eval` | Eval-specific test dependencies |
| `e2e` | BDD test dependencies |

Provider SDK imports are always lazy (inside methods or guarded by the factory match) so the base package imports cleanly without any extras installed.
