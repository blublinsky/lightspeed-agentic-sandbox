# E2E container BDD harness

Meta-spec for **how** live end-to-end tests run in this repository. Behavioral
rules for the batch entrypoint, readiness helpers, and providers live in the other
`what/` specs; this document maps scenarios to those rules and records spike decisions for
[OLS-3220](https://redhat.atlassian.net/browse/OLS-3220)

> **Transitional state:** The sandbox no longer exposes HTTP (`app.py`, `/health`,
> `/ready`, `/v1/agent/run` removed). The BDD harness (`runner.py`, `e2e-containers.sh`,
> feature files) still targets HTTP and is **[PLANNED: migrate to batch]**. Unit tests
> (`test_run_agent.py`, `test_batch.py`, `test_ready.py`) cover batch behavior today.

## Spike findings (OLS-3220)

Investigation goal: add BDD coverage for health probes, context prefix, and run
error handling without flaky live LLM assertions.

### Feasible in live container BDD

| Area | Approach | Artifact |
|------|----------|----------|
| Liveness / readiness happy path | Direct HTTP GET; deterministic status and JSON shape | [sandbox_e2e.feature](../../../tests/e2e/features/sandbox_e2e.feature) |
| Run timeout envelope | `timeout_ms=1` on a long-running query → HTTP 200, `success=false` | [sandbox_e2e.feature](../../../tests/e2e/features/sandbox_e2e.feature) |
| Context reaches the model | **Structured echo**: prepared `context` (`targetNamespaces`, `previousAttempts`, `approvedOption`) + `outputSchema`; model echoes back as response fields (`namespaces`, `firstFailureReason`, `approvedTitle`/`rootCause`) | [sandbox_e2e.feature](../../../tests/e2e/features/sandbox_e2e.feature) |
| Structured output / skills | Existing scenarios unchanged | [structured_output.feature](../../../tests/e2e/features/structured_output.feature), [skills.feature](../../../tests/e2e/features/skills.feature) |
| MCP connectivity | Live/container scenarios for MCP wiring | [mcp.feature](../../../tests/e2e/features/mcp.feature) |
| Reasoning config | Live/container scenarios | [reasoning_config.feature](../../../tests/e2e/features/reasoning_config.feature) |

Context proof is **semantic** (model output reflects injected context), not
inspection of the composed `[context]` prefix string. Exact prefix formatting
belongs in unit tests.

### Not feasible / intentionally unit-only

| Area | Reason | Artifact |
|------|--------|----------|
| Exact `[context]` prefix text | Deterministic formatting; no need for live LLM | [test_run_agent.py](../../../tests/test_run_agent.py) (`format_context_prefix`) |
| Empty provider result (run-api rule 23) | Requires mocked provider; unreliable with live models | [test_run_agent.py](../../../tests/test_run_agent.py) |
| Readiness R1 when credentials missing | Needs deliberately misconfigured runtime; covered without live network | [test_ready.py](../../../tests/test_ready.py) |
| HTTP 500 on adversarial schema (rule 22) | Live suite asserts envelope via HTTP; unit tests cover batch path | [structured_output.feature](../../../tests/e2e/features/structured_output.feature), [test_run_agent.py](../../../tests/test_run_agent.py) |

### Unimplemented / uncovered

| Area | Reason | Artifact |
|------|--------|----------|
| Readiness rule R3 (MCP reachability) | Not implemented; no tracked story | — |

### Design decisions

- **One feature file** for OLS-3220 scenarios: `sandbox_e2e.feature` (probes,
  timeout, context echo) instead of three separate files. Same scenarios, less
  glue duplication.
- **`runner.py` extensions**: `get_json()` for probe GETs; `context=` on
  `run_query()` for POST `/v1/agent/run`.
- **Two run modes** (see [Harness](#harness) below): container image (local dev)
  and `--prow-host` (host uvicorn for OpenShift CI without podman).
- **Skill token output**: `E2E_OUTPUT_DIR` is a host tmpdir; OpenAI
  `UnixLocalSandbox` only allows writes under the skills tree unless
  `extra_path_grants` includes that path (see `openai.py`). Tmpdir is removed
  after pytest; optional copy to `ARTIFACT_DIR` on Prow.

- **Multi-provider matrix** — ticket AC requires at least one provider; OpenAI
  validated on `--prow-host`. Claude/Gemini optional before merge.

## Relationship to behavioral specs

| Behavioral spec | This harness exercises |
|-----------------|------------------------|
| [run-api.md](run-api.md) | Timeout (rule 21), context wiring (rules 4, 7, 12–16); rules 22–23 via unit tests |
| [health-probes.md](health-probes.md) | Batch startup readiness (R1); legacy HTTP probe BDD pending migration |
| [provider-contract.md](provider-contract.md) | Structured output and skills via existing feature files |
| [configuration.md](configuration.md) | Model/env resolution implicit in container and prow-host startup |

Do **not** duplicate behavioral rules here. When adding a scenario, update the
relevant `what/` spec Verification table first, then the feature file.

## Harness

### Layout

```text
tests/e2e/
├── features/           # Gherkin scenarios
├── steps/              # given / when / then step definitions
├── runner.py           # HTTP client (GET probes, POST /run)
├── conftest.py         # fixtures: server_url, e2e_output_dir, bdd_context
├── credentials.py      # preflight credential checks per provider
├── config.env          # default models for e2e (sourced in clean env)
└── pytest.ini          # e2e collection config

scripts/e2e-containers.sh   # start sandbox, export env, run pytest
```

### Run modes

**Container (default)** — requires podman or docker:

```bash
make e2e openai-agents
# or: bash scripts/e2e-containers.sh openai-agents [model-override]
# matrix ids: anthropic-vertex-deepagents | gemini-vertex-adk | openai-agents
```

Builds or uses `IMAGE`, mounts skills workspace and tmp output dir, runs one
provider per process, exports `SANDBOX_SERVICE_URL` and `E2E_PROVIDER` for pytest.

**Prow host** — no container runtime; uvicorn on the host (OpenShift CI):

```bash
E2E_SKIP_INSTALL=1 bash scripts/e2e-containers.sh --prow-host openai-agents
# optional model: ... --prow-host openai-agents gpt-5-mini
```

Uses `tests/e2e/config.env` models in a clean env (avoids host shell pollution
e.g. `OPENAI_MODEL=claude-…`). LLM credentials may be copied under
`.e2e/llm-credentials` when `/var/run/secrets` is not writable.

### Environment exports

| Variable | Set by | Purpose |
|----------|--------|---------|
| `SANDBOX_SERVICE_URL` | `e2e-containers.sh` | Base URL for pytest (app root, not `/v1/agent`) |
| `E2E_PROVIDER` | `e2e-containers.sh` | Provider name for credential checks / logging |
| `E2E_OUTPUT_DIR` | `e2e-containers.sh` | Host path where skill tools write `.e2e_token` |
| `E2E_ARGS` | operator | Extra pytest args (e.g. `-v`, `-k`) |
| `ARTIFACT_DIR` | Prow | Token output copied before tmp cleanup; pytest tee'd to `e2e-<provider>-pytest.log` and `e2e-<provider>-summary.txt` (alongside `junit_e2e.xml` from `E2E_ARGS`) |

### Flake policy

- Prefer **deterministic HTTP assertions** (status codes, envelope fields) over
  free-text LLM output when possible.
- Live context scenarios use **structured output** with strict echo instructions
  in the system prompt and schema.
- Scenarios that depend on provider timing (timeout with `timeout_ms=1`) assert
  the **response envelope**, not whether the provider finished mid-flight.
- Do not add live tests that require missing credentials, broken endpoints, or
  empty model output unless the harness gains a fake-provider mode.

## Verification map

Feature files and unit tests are also listed under each behavioral spec. Summary:

| Feature file | Primary spec | Scenarios |
|--------------|--------------|-----------|
| [sandbox_e2e.feature](../../../tests/e2e/features/sandbox_e2e.feature) | run-api, health-probes (legacy HTTP) | Probes, timeout, context echo — harness pending batch migration |
| [structured_output.feature](../../../tests/e2e/features/structured_output.feature) | run-api, provider-contract | JSON schema, text fallback, adversarial schema |
| [skills.feature](../../../tests/e2e/features/skills.feature) | provider-contract | Skills mount, echo-token skill, nonskill query |
| [mcp.feature](../../../tests/e2e/features/mcp.feature) | provider-contract, configuration, health-probes | MCP connectivity wiring, credential/header resolution, `/health` |
| [reasoning_config.feature](../../../tests/e2e/features/reasoning_config.feature) | provider-contract, configuration | Reasoning/thinking config passthrough |
| [troubleshooting.feature](../../../tests/e2e/features/troubleshooting.feature) | e2e-testing (troubleshooting) | Cluster-level troubleshooting scenario validation (OLS-3739) |

Unit tests: [test_run_agent.py](../../../tests/test_run_agent.py),
[test_batch.py](../../../tests/test_batch.py),
[test_ready.py](../../../tests/test_ready.py).

## Troubleshooting scenario tests (OLS-3739)

Cluster-level BDD tests that exercise the full AgenticRun lifecycle against
real OpenShift clusters with injected broken states. These tests verify the
**quality and correctness of sandbox output** — phase transition testing is the
operator's responsibility (see lightspeed-agentic-operator specs).

### Scope

- **In scope:** BDD scenarios that inject broken cluster state, create
  AgenticRun CRs via the `kubernetes` Python client, wait for completion, read
  AnalysisResult/ExecutionResult/VerificationResult CRs and sandbox pod logs,
  assert domain-keyword presence, and run an LLM judge for output relevance.
- **Out of scope:** Phase transition assertions (operator product-e2e),
  behavioral correctness of execution fixes (future work).

### Prerequisites

- Running sandbox service (same as existing e2e)
- Operator deployed on a live OpenShift cluster
- `kubernetes` Python client (new test dependency)
- KUBECONFIG with permissions to create/delete namespaces, deployments, and
  AgenticRun CRs
- LLM provider credentials (same as existing e2e)

### Scenarios

Troubleshooting scenario scripts live in `scenarios/troubleshooting/` at the
repository root. Each scenario directory contains `setup.sh` (inject broken
state), `cleanup.sh` (restore). A shared `scenario_metadata.yaml` at the
`scenarios/troubleshooting/` root maps scenario IDs to AgenticRun request text
and expected domain keywords.

| Scenario ID | AgenticRun request | Expected keywords |
|---|---|---|
| `envvar_missing` | Diagnose CrashLoopBackOff in warehouse-ops | `CrashLoopBackOff`, `DEPLOY_ENV` |
| `batch_failure` | Diagnose job failure | `job`, `fail` |
| `storage_binding` | Diagnose PVC issue | `PersistentVolumeClaim`, `bound` |
| `namespace_pod_count` | Count pods in fleet-alpha | `fleet-alpha`, `pod` |
| `scheduled_outage_detection` | Detect API outage window | `outage`, `03:00` |
| `periodic_failure_window` | Detect periodic failure | `failure`, `03:00` |
| `config_drift_analysis` | Diagnose connection refused | `connection refused`, `config` |
| `readiness_probe_diagnosis` | Diagnose readiness probe failure | `readiness`, `probe` |
| `ingress_rule_mismatch` | Diagnose NetworkPolicy blocking | `NetworkPolicy`, `traffic` |
| `oom` | Diagnose OOMKilled | `OOMKilled` |
| `wrong_networkpolicy` | Diagnose and fix NetworkPolicy | `NetworkPolicy` |

Setup/cleanup scripts run on the test host via `subprocess` — they are Bash scripts
that manipulate cluster state with `kubectl` (see `scenarios/troubleshooting/lib.sh`).
AgenticRun and Result CR lifecycle in tests use the `kubernetes` Python client, not shell.

### BDD structure

Feature file: `tests/e2e/features/troubleshooting.feature`

Scenario outline parametrized over the 11 scenarios. Each scenario:
1. Injects broken cluster state via `setup.sh`
2. Creates AgenticRun CR via `kubernetes.client.CustomObjectsApi`
3. Polls until AgenticRun reaches `Completed` phase (or timeout)
4. Reads AnalysisResult/ExecutionResult/VerificationResult CRs
5. Reads sandbox pod logs via `kubernetes.client.CoreV1Api`
6. Asserts expected domain keywords in result content
7. Calls LLM judge to verify output relevance
8. Runs `cleanup.sh` (always, even on failure)

Step definitions extend the existing `tests/e2e/steps/` modules. New fixtures
in `tests/e2e/conftest.py`:
- `k8s_client` — authenticated `CustomObjectsApi` from KUBECONFIG
- `k8s_core_client` — `CoreV1Api` for pod log retrieval
- `scenario_cleanup` — yield fixture ensuring cleanup.sh runs

### LLM judge

A utility module that takes scenario context (ID, request, expected keywords)
plus sandbox output (analysis/execution/verification results, pod logs) and
asks the configured LLM whether the output correctly identifies and addresses
the scenario's problem. Returns pass/fail with reasoning.

- Model configurable via `E2E_JUDGE_MODEL` env var
- Defaults to the same provider/model that ran the AgenticRun
- Uses provider credentials already available in the e2e environment

### Run mode

Cluster e2e is a separate entry point from the existing container/prow-host
modes. It requires both the sandbox service AND a live cluster with operator.

```bash
make e2e-cluster <provider>
# e.g.: make e2e-cluster openai-agents
```

`scripts/e2e-cluster.sh` handles environment setup, runs only the
troubleshooting feature file, and collects artifacts.

### Environment exports

| Variable | Set by | Purpose |
|----------|--------|---------|
| `KUBECONFIG` | User/CI | Cluster access for kubernetes client |
| `E2E_JUDGE_MODEL` | Optional | Override LLM judge model (default: run provider model) |
| `E2E_SCENARIOS_DIR` | `e2e-cluster.sh` | Path to scenario scripts (default: `scenarios/troubleshooting/`) |
| `E2E_OPERATOR_NAMESPACE` | `e2e-cluster.sh` | Namespace where operator is deployed (default: `openshift-lightspeed`) |

### Flake policy

- Scenario setup/cleanup scripts MUST be idempotent
- AgenticRun polling uses configurable timeout (default: 20m per scenario)
- LLM judge assertions are logged but SHOULD NOT cause hard test failure in
  initial rollout — keyword assertions are the primary gate
- Cleanup runs in a finally/yield block regardless of test outcome

### Future work

- [PLANNED] **Behavioral correctness assertions:** verify that ExecutionResult
  actually attempted a fix (e.g., patched a resource, adjusted limits) and
  VerificationResult confirmed or denied the fix worked
- [PLANNED] **LLM judge as hard gate:** once confidence in judge reliability is
  established, promote judge pass/fail to a hard test assertion

## Commands

```bash
make install-all          # providers + e2e extras (first time)
make test                 # unit only; no credentials
make e2e openai-agents    # live BDD, container mode
make e2e-cluster openai-agents  # cluster BDD, troubleshooting scenarios
E2E_SKIP_INSTALL=1 E2E_ARGS="-v" bash scripts/e2e-containers.sh --prow-host openai-agents
```
