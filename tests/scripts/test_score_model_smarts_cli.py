from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.model_smarts import score_artifact


def test_score_artifact_from_csv_and_json(tmp_path: Path) -> None:
    csv_path = tmp_path / "results.csv"
    csv_path.write_text(
        "run_id,model_name,model_label,endpoint,test_id,tier,prompt_name,elapsed_seconds,finish_reason,shape,failure_label,content_preview,reasoning_preview,notes\n"
        "run-1,model-a,alpha,http://example/v1,T1-1,T1,Ordered planning under constraints,1.0,stop,content_only,ok,1. Plan. 2. Do.,,\n"
        "run-1,model-b,beta,http://example/v1,T1-1,T1,Ordered planning under constraints,1.0,length,content_only,ok,A very long answer that ignores the constraints.,,\n",
        encoding="utf-8",
    )

    json_path = tmp_path / "results.raw.json"
    json_path.write_text(
        json.dumps(
            {
                "run_id": "run-2",
                "models": [
                    {
                        "name": "model-c",
                        "label": "gamma",
                        "endpoint": "http://example/v1",
                        "tests": [
                            {
                                "test_id": "T1-4",
                                "prompt_name": "Focused summarization",
                                "finish_reason": "stop",
                                "shape": "content_only",
                                "content_preview": "Please provide the situation you would like me to summarize.",
                            }
                        ],
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    csv_report = score_artifact(csv_path)
    json_report = score_artifact(json_path)

    assert len(csv_report.rows) == 2
    assert [model.model_name for model in csv_report.models] == ["model-a", "model-b"]
    assert csv_report.models[0].score > csv_report.models[1].score
    assert json_report.models[0].model_name == "model-c"
    assert json_report.models[0].score >= 0.75


def test_cli_outputs_table(tmp_path: Path) -> None:
    csv_path = tmp_path / "results.csv"
    csv_path.write_text(
        "run_id,model_name,model_label,endpoint,test_id,tier,prompt_name,elapsed_seconds,finish_reason,shape,failure_label,content_preview,reasoning_preview,notes\n"
        "run-1,model-a,alpha,http://example/v1,T1-1,T1,Ordered planning under constraints,1.0,stop,content_only,ok,1. Plan. 2. Do.,,\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/score_model_smarts.py",
            str(csv_path),
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "model-a" in proc.stdout
    assert "smarts" in proc.stdout.lower()


def test_cli_outputs_json(tmp_path: Path) -> None:
    csv_path = tmp_path / "results.csv"
    csv_path.write_text(
        "run_id,model_name,model_label,endpoint,test_id,tier,prompt_name,elapsed_seconds,finish_reason,shape,failure_label,content_preview,reasoning_preview,notes\n"
        "run-1,model-a,alpha,http://example/v1,T1-1,T1,Ordered planning under constraints,1.0,stop,content_only,ok,1. Plan. 2. Do.,,\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/score_model_smarts.py",
            "--json",
            str(csv_path),
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["artifacts"][0]["path"].endswith("results.csv")
    assert payload["artifacts"][0]["models"][0]["model_name"] == "model-a"
