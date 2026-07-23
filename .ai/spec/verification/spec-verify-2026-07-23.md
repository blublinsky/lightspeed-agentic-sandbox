# Verification Report: lightspeed-agentic-sandbox Spec
Verified: 2026-07-23
Spec root: /Users/xavi/street/github.com/AI/ols/lightspeed-agentic-sandbox/.ai/spec/

## Summary
- 0 broken or inaccurate internal references
- 2 internal inconsistencies
- 2 completeness gaps
- 1 cross-repo alignment issue

## Reference Issues

None. All internal references verified:
- All 16 referenced test/e2e files exist
- All 17 referenced source files exist
- Parent spec cross-references exist (templog.md, audit-logging.md)
- README cross-reference table (what/ to how/ mapping) is accurate: all 6 entries verified

## Internal Inconsistencies

**I1. `audit-logging.md` rule numbering collision.**
Rules 8 and 8a coexist: rule 8 ("The sandbox MUST emit gen_ai.choice span events...") and rule 8a ("Content Capture Policy"). Rule 8a should be renumbered to 9 and subsequent rules shifted, or 8a merged into rule 8 with a consistent sub-rule convention.

**I2. `run-api.md` duplicates health/ready endpoint definitions from `health-probes.md`.**
`run-api.md` rules 10-11 define `/health` and `/ready` endpoint behavior (response shapes, HTTP codes), while `health-probes.md` provides the authoritative, detailed version. `run-api.md` notes "Rules 10-11 are verified under health-probes.md, not here" — but if either file is edited in isolation the duplicate definitions could diverge.

## Completeness Gaps

**G1. `decisions/` directory is empty.**
`decisions/README.md` template exists but no ADRs recorded. `e2e-testing.md` has a "Design decisions" section documenting OLS-3220 spike decisions inline. Key decisions worth formalizing: MCP transport choice (Streamable HTTP over SSE, `configuration.md` rule 22), Claude-to-DeepAgents migration (OLS-3500), structured-output Pydantic subset limitation.

**G2. No `glossary.md`.**
Terms like "DeepAgents," "thin-adapter principle," "ProviderQueryOptions," "ResolvedSDK," "sandbox-claim mode," "SkillsMiddleware" are used across multiple spec files without central definition. Especially ambiguous: "provider" means both the hosting backend (e.g., `anthropic`) and the SDK (e.g., `deepagents`) depending on context — clarified in `configuration.md` rule 2's mapping table but not surfaced elsewhere.

## Cross-Repo Alignment Issues

**A1. Parent spec `agentic-runs.md` still references "Claude" adapter.**
Two locations in the parent spec use outdated terminology:
- Rule 10: "The sandbox executes the request using the configured LLM provider (Claude, Gemini, or OpenAI)"
- Repo Ownership table: "LLM provider abstraction (Claude/Gemini/OpenAI adapters)"

The sandbox spec's `provider-contract.md` rules 19 and 31 explicitly state: "Claude adapter was removed in OLS-3500; Anthropic reasoning/MCP is now handled by the DeepAgents adapter." The parent spec should be updated to say "Anthropic (via DeepAgents)" instead of "Claude."

## Files Checked

### what/ (7 files)
- system-overview.md, run-api.md (24 rules), provider-contract.md (38 rules, 2 removed), configuration.md (22 rules), health-probes.md, audit-logging.md (26 rules), e2e-testing.md

### how/ (2 files)
- project-structure.md, provider-architecture.md

### Other
- README.md, decisions/README.md (empty ADR template)
- No constraints.md (inline per convention), no glossary.md

### Cross-repo
- /Users/xavi/street/github.com/AI/ols/.ai/spec/what/agentic-security.md (no alignment issues)
- /Users/xavi/street/github.com/AI/ols/.ai/spec/what/agentic-runs.md (1 alignment issue)
