#!/usr/bin/env python3
"""比较第二版原始信息增益与可回答性感知策略，仅用于开发分析。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.evaluate_frozen_test import run_strategy_case, summarize_strategy  # noqa: E402
from src.diagnosis.models import DiagnosisState  # noqa: E402
from src.diagnosis.policies import (  # noqa: E402
    InformationGainPolicy,
    PureInformationGainPolicy,
)
from src.diagnosis.service_v2 import DiagnosisServiceV2  # noqa: E402

CASES_PATH = ROOT / "data/evaluation/public_cases.json"
SPLIT_PATH = ROOT / "data/evaluation/real_case_split.json"
OUTPUT_PATH = ROOT / "data/evaluation/v2_strategy_development_results.json"


def evaluate() -> dict:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    by_id = {case["id"]: case for case in cases}
    split = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
    cohorts = {
        "original_development": split["development_ids"],
        "visible_frozen_feedback": split["frozen_test_ids"],
    }
    policies = {
        "pure_information_gain": PureInformationGainPolicy,
        "answerability_aware": InformationGainPolicy,
    }

    summaries = []
    details: dict[str, dict[str, list[dict]]] = {}
    for cohort, ids in cohorts.items():
        cohort_cases = [by_id[case_id] for case_id in ids]
        details[cohort] = {}
        for strategy, policy_type in policies.items():
            service = DiagnosisServiceV2()
            rows = [
                run_strategy_case(service, case, policy_type())
                for case in cohort_cases
            ]
            details[cohort][strategy] = rows
            summaries.append(summarize_strategy(strategy, rows, len(rows)) | {
                "cohort": cohort
            })

    initial_question_differences = []
    service = DiagnosisServiceV2()
    for case_id in [*cohorts["original_development"], *cohorts["visible_frozen_feedback"]]:
        case = by_id[case_id]
        snapshot = service.start(case["report"])
        state = DiagnosisState.from_dict(snapshot["state"])
        pure = PureInformationGainPolicy().choose(service.engine, state)
        full = InformationGainPolicy().choose(service.engine, state)
        if pure and full and pure.name != full.name:
            initial_question_differences.append(
                {
                    "id": case_id,
                    "pure": {
                        "name": pure.name,
                        "information_gain": pure.information_gain,
                        "answerability": pure.answerability,
                        "cost": pure.cost,
                    },
                    "answerability_aware": {
                        "name": full.name,
                        "information_gain": full.information_gain,
                        "answerability": full.answerability,
                        "cost": full.cost,
                        "utility": full.utility,
                    },
                }
            )

    return {
        "benchmark": "debugpath-v2-strategy-development-v1",
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "warning": "全部案例均已被开发者查看；结果只解释算法行为，不是第二版无偏测试成绩。",
        "strategies": {
            "pure_information_gain": "只按理论熵下降选问",
            "answerability_aware": "理论熵下降乘可回答率，再扣除检查成本与风险成本",
        },
        "summaries": summaries,
        "initial_question_difference_count": len(initial_question_differences),
        "initial_question_differences": initial_question_differences,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = evaluate()
    for item in report["summaries"]:
        print(
            f"{item['cohort']} / {item['strategy']}: "
            f"Top-1={item['top1']:.1%}，覆盖率={item['coverage']:.1%}，"
            f"平均追问={item['avg_questions']:.2f}"
        )
    print(f"初始选问不同：{report['initial_question_difference_count']}条")
    print(report["warning"])
    if args.write:
        OUTPUT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"已写入：{OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
