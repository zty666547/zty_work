#!/usr/bin/env python3
"""从网页导出的第二版案例中汇总问题可回答率和回答成本。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.diagnosis.calibration import calibrate_question_observations  # noqa: E402


def load_cases(paths: list[Path]) -> list[dict]:
    cases = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "debugpath-case-v2":
            raise ValueError(f"{path}不是DebugPath第二版案例")
        cases.append(payload)
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cases", nargs="+", type=Path)
    parser.add_argument("--minimum-samples", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.minimum_samples < 1:
        raise SystemExit("minimum-samples必须大于0")
    report = calibrate_question_observations(
        load_cases(args.cases), minimum_samples=args.minimum_samples
    )
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(content, encoding="utf-8")
        print(f"已写入：{args.output}")
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
