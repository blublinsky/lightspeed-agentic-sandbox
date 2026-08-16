"""Tests for batch input file reading."""

from __future__ import annotations

import json

import pytest

from lightspeed_agentic.batch import InputReadError, read_batch_inputs


def _write_input(tmp_path, **files: str) -> str:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    for name, content in files.items():
        (input_dir / name).write_text(content, encoding="utf-8")
    return str(input_dir)


class TestReadBatchInputs:
    def test_reads_required_files(self, tmp_path) -> None:
        input_dir = _write_input(
            tmp_path,
            query="fix the pod",
            **{
                "output-schema": json.dumps({"type": "object"}),
                "context": json.dumps({"targetNamespaces": ["default"]}),
                "result-template": json.dumps(
                    {
                        "apiVersion": "agentic.openshift.io/v1alpha1",
                        "kind": "AnalysisResult",
                        "metadata": {"name": "run-analysis-1", "namespace": "ns"},
                    }
                ),
            },
        )

        inputs = read_batch_inputs(input_dir)
        assert inputs.query == "fix the pod"
        assert inputs.output_schema == {"type": "object"}
        assert inputs.context["targetNamespaces"] == ["default"]
        assert inputs.result_template["kind"] == "AnalysisResult"
        assert inputs.system_prompt is None

    def test_optional_system_prompt_absent(self, tmp_path) -> None:
        input_dir = _write_input(
            tmp_path,
            query="q",
            **{
                "output-schema": "{}",
                "context": "{}",
                "result-template": json.dumps({"kind": "AnalysisResult"}),
            },
        )
        inputs = read_batch_inputs(input_dir)
        assert inputs.system_prompt is None

    def test_optional_system_prompt_present(self, tmp_path) -> None:
        input_dir = _write_input(
            tmp_path,
            query="q",
            **{
                "output-schema": "{}",
                "context": "{}",
                "result-template": json.dumps({"kind": "AnalysisResult"}),
                "system-prompt": "You are a test agent.",
            },
        )
        inputs = read_batch_inputs(input_dir)
        assert inputs.system_prompt == "You are a test agent."

    def test_missing_required_file_raises(self, tmp_path) -> None:
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "query").write_text("q", encoding="utf-8")

        with pytest.raises(InputReadError, match="read"):
            read_batch_inputs(str(input_dir))

    def test_invalid_json_raises(self, tmp_path) -> None:
        input_dir = _write_input(
            tmp_path,
            query="q",
            **{
                "output-schema": "{bad",
                "context": "{}",
                "result-template": "{}",
            },
        )

        with pytest.raises(InputReadError, match="invalid JSON"):
            read_batch_inputs(input_dir)

    def test_invalid_utf8_raises(self, tmp_path) -> None:
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "query").write_bytes(b"\xff\xfe")

        with pytest.raises(InputReadError, match="invalid UTF-8"):
            read_batch_inputs(str(input_dir))
