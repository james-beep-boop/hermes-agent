#!/usr/bin/env python3
"""Score local-model benchmark artifacts with the heuristic smarts metric.

Usage:
    python scripts/score_model_smarts.py path/to/results.csv [more artifacts...]
    python scripts/score_model_smarts.py --json path/to/results.raw.json

Supported artifacts:
- CSV benchmark exports with the usual Hermes result columns
- Raw JSON rerun artifacts with a top-level ``models`` list
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.model_smarts import score_artifacts


def _format_table(report) -> str:
    lines = [
        f"Smarts score for {report.path} ({report.format})",
        "-" * 90,
        f"{'rank':>4}  {'model':<46} {'label':<16} {'score':>7} {'rows':>5}",
    ]
    for idx, model in enumerate(report.models, start=1):
        label = model.model_label or "-"
        lines.append(
            f"{idx:>4}  {model.model_name:<46.46} {label:<16.16} {model.score:>7.4f} {model.row_count:>5}"
        )
    if len(report.models) == 0:
        lines.append("(no model rows found)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", nargs="+", help="CSV or raw JSON benchmark artifact(s)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    reports = score_artifacts(args.artifacts)
    if args.json:
        payload = {
            "artifacts": [
                {
                    "path": report.path,
                    "format": report.format,
                    "models": [
                        {
                            "model_name": model.model_name,
                            "model_label": model.model_label,
                            "endpoint": model.endpoint,
                            "score": model.score,
                            "row_count": model.row_count,
                        }
                        for model in report.models
                    ],
                }
                for report in reports
            ]
        }
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    for i, report in enumerate(reports):
        if i:
            sys.stdout.write("\n")
        sys.stdout.write(_format_table(report))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
