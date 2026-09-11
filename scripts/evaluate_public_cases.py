#!/usr/bin/env python3
"""在根因已确认的公开案例种子上运行新旧主动诊断算法。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import Settings  # noqa: E402
from scripts.evaluate_active_algorithm import run_case, summarize  # noqa: E402
from src.diagnosis.service import DiagnosisService  # noqa: E402

DATASET = ROOT / "data/evaluation/public_cases.json"
SPLIT_DATASET = ROOT / "data/evaluation/real_case_split.json"
OUTPUT = ROOT / "data/evaluation/public_case_results.json"


def load_public_cases() -> tuple[list[dict], list[dict]]:
    payload = json.loads(DATASET.read_text(encoding="utf-8"))
    cases = payload["cases"]
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("公开案例ID重复")
    for case in cases:
        if not case["source_url"].startswith("https://github.com/"):
            raise ValueError(f"{case['id']}缺少公开GitHub来源")
        if case["root_cause_status"] not in {"confirmed", "unconfirmed"}:
            raise ValueError(f"{case['id']}的根因状态非法")
    confirmed = [case for case in cases if case["root_cause_status"] == "confirmed"]
    pending = [case for case in cases if case["root_cause_status"] == "unconfirmed"]
    return confirmed, pending


def evaluate() -> dict:
    confirmed, pending = load_public_cases()
    split = json.loads(SPLIT_DATASET.read_text(encoding="utf-8"))
    development_ids = set(split["development_ids"])
    development = [case for case in confirmed if case["id"] in development_ids]
    if len(development) != len(development_ids):
        raise ValueError("开发集清单与公开案例文件不一致")
    algorithms = [
        (
            "legacy_information_gain",
            DiagnosisService(
                Settings(
                    enable_answerability_adjustment=False,
                    enable_robust_stopping=False,
                )
            ),
        ),
        ("answerability_aware", DiagnosisService(Settings())),
    ]
    details = {
        name: [run_case(service, case, unknown_below=0.0) for case in development]
        for name, service in algorithms
    }
    return {
        "benchmark": "public_real_case_development_set",
        "development_cases": len(development),
        "confirmed_cases": len(confirmed),
        "frozen_test_cases": len(split["frozen_test_ids"]),
        "unconfirmed_cases": len(pending),
        "warning": "结果来自已查看的开发集，只能用于调整算法；冻结测试集收集完成前不得报告最终性能。",
        "metrics": [summarize(name, details[name]) for name, _ in algorithms],
        "details": details,
        "unconfirmed_ids": [case["id"] for case in pending],
    }


def main() -> None:
    report = evaluate()
    print(
        f"真实开发集：{report['development_cases']}；"
        f"冻结测试集：{report['frozen_test_cases']}；"
        f"待确认：{report['unconfirmed_cases']}"
    )
    for row in report["metrics"]:
        print(
            f"{row['algorithm']}: Top-1={row['top1']:.1%}, "
            f"覆盖率={row['coverage']:.1%}, "
            f"平均追问={row['avg_questions']:.2f}, "
            f"平均无法回答={row['avg_unknown_questions']:.2f}"
        )
    print("注意：当前是开发集结果，冻结测试集收集完成前不得作为最终算法结论。")
    OUTPUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
