"""E2E fixtures — single provider per process (no parametrization)."""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pytest
from kubernetes import config as k8s_config  # type: ignore[import-untyped]
from kubernetes.client import ApiClient, CoreV1Api, CustomObjectsApi  # type: ignore[import-untyped]

from tests.e2e.runner import RunHttpResult, run_query
from steps.given import *  # noqa: F403 — step fixtures must be in conftest namespace
from steps.when import *  # noqa: F403
from steps.then import *  # noqa: F403


@pytest.fixture
def bdd_context() -> dict[str, Any]:
    return {}


@pytest.fixture(scope="session")
def server_url() -> str:
    url = os.environ.get("SANDBOX_SERVICE_URL", "").strip()
    if not url:
        pytest.fail("SANDBOX_SERVICE_URL is not set (use scripts/e2e-containers.sh or export it)")
    return url.rstrip("/")


@pytest.fixture(scope="session")
def provider_name() -> str:
    name = os.environ.get("E2E_PROVIDER", "").strip()
    if not name:
        pytest.fail("E2E_PROVIDER is not set (e2e-containers.sh exports it)")
    return name


@pytest.fixture
def e2e_output_dir() -> Path | None:
    """Host-side output directory where skill tools write token files."""
    raw = os.environ.get("E2E_OUTPUT_DIR", "").strip()
    if not raw:
        return None
    return Path(raw)


@pytest.fixture(scope="session")
def _k8s_config_loaded() -> None:
    """Load kubeconfig once per session."""
    k8s_config.load_kube_config()


@pytest.fixture(scope="session")
def _k8s_api_client(_k8s_config_loaded: None) -> ApiClient:
    return ApiClient()


@pytest.fixture(scope="session")
def k8s_client(_k8s_api_client: ApiClient) -> CustomObjectsApi:
    """Authenticated CustomObjectsApi from KUBECONFIG."""
    return CustomObjectsApi(_k8s_api_client)


@pytest.fixture(scope="session")
def k8s_core_client(_k8s_api_client: ApiClient) -> CoreV1Api:
    """Authenticated CoreV1Api for pod log retrieval."""
    return CoreV1Api(_k8s_api_client)


@pytest.fixture
def scenario_cleanup() -> Generator[None, None, None]:
    """Yield fixture that runs cleanup.sh on test teardown.

    Expects SCENARIO_DIR env var to point to the scenario directory
    containing cleanup.sh. Skips cleanup if not set.
    """
    yield
    scenario_dir = os.environ.get("SCENARIO_DIR", "").strip()
    if not scenario_dir:
        return
    cleanup_script = Path(scenario_dir) / "cleanup.sh"
    if cleanup_script.is_file():
        result = subprocess.run(  # noqa: S603
            ["bash", str(cleanup_script)],  # noqa: S607
            check=False,
            capture_output=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger = logging.getLogger(__name__)
            logger.warning(
                "cleanup.sh exited %d\nstderr: %s",
                result.returncode,
                result.stderr.decode(errors="replace").strip(),
            )


@pytest.fixture
def run_runner(server_url: str) -> Callable[..., RunHttpResult]:
    def _run(
        query: str,
        *,
        system_prompt: str = "You are a helpful assistant. Follow instructions exactly.",
        output_schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        timeout_ms: int | None = None,
    ) -> RunHttpResult:
        return run_query(
            server_url,
            query,
            system_prompt=system_prompt,
            output_schema=output_schema,
            context=context,
            timeout_ms=timeout_ms,
        )

    return _run
