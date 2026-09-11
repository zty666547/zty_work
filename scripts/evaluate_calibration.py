#!/usr/bin/env python3
"""在真实开发集上拆分验证两项因果模型修改的贡献。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.evaluate_active_algorithm import run_case, summarize  # noqa: E402
from src.diagnosis.service import DiagnosisService  # noqa: E402

CASES_PATH = ROOT / "data/evaluation/public_cases.json"
SPLIT_PATH = ROOT / "data/evaluation/real_case_split.json"
OUTPUT_PATH = ROOT / "data/evaluation/calibration_results.json"

HOST_QUESTION = "Q-目标主机本机检查是否成功"
HOST_OBSERVATION = "O-目标主机本机检查成功"
PACKAGE_OBSERVATION = "O-当前环境可见目标包"
VERSION_CAUSE = "Python版本与包不兼容"
SERVICE_ISSUE = "服务或配置连接失败"


def _development_cases() -> list[dict]:
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    split = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
    development_ids = set(split["development_ids"])
    return [case for case in payload["cases"] if case["id"] in development_ids]


def _service(*, recalibrate_package: bool, add_host_question: bool) -> DiagnosisService:
    service = DiagnosisService()
    service.engine.observation_effects[PACKAGE_OBSERVATION][VERSION_CAUSE] = (
        0.25 if recalibrate_package else 0.80
    )
    if not add_host_question:
        service.engine.issue_questions[SERVICE_ISSUE] = [
            item
            for item in service.engine.issue_questions[SERVICE_ISSUE]
            if item["name"] != HOST_QUESTION
        ]
        service.engine.question_observation.pop(HOST_QUESTION, None)
        service.engine.observation_effects.pop(HOST_OBSERVATION, None)
    return service


def evaluate() -> dict:
    cases = _development_cases()
    variants = [
        ("before_calibration", False, False),
        ("package_likelihood_only", True, False),
        ("host_local_question_only", False, True),
        ("combined", True, True),
    ]
    details = {}
    metrics = []
    for name, package, host_question in variants:
        rows = [
            run_case(
                _service(
                    recalibrate_package=package,
                    add_host_question=host_question,
                ),
                case,
                unknown_below=0.0,
            )
            for case in cases
        ]
        details[name] = rows
        metrics.append(summarize(name, rows))
    return {
        "benchmark": "real_case_development_calibration_ablation",
        "case_count": len(cases),
        "warning": "仅用于开发集内选择模型结构与参数，不是冻结测试结果。",
        "metrics": metrics,
        "details": details,
    }


def main() -> None:
    report = evaluate()
    print("配置                         Top-1  覆盖率  平均追问  无法回答")
    print("-" * 73)
    for row in report["metrics"]:
        print(
            f"{row['algorithm']:<28} {row['top1']:>6.1%} "
            f"{row['coverage']:>6.1%} {row['avg_questions']:>9.2f} "
            f"{row['avg_unknown_questions']:>9.2f}"
        )
    OUTPUT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\n完整结果已写入 {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
