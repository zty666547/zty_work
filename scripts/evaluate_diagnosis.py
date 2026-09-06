#!/usr/bin/env python3
"""在同一冻结案例集上比较四种诊断选问策略。"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.diagnosis.models import DiagnosisState  # noqa: E402
from src.diagnosis.policies import (  # noqa: E402
    DirectPolicy,
    FixedOrderPolicy,
    InformationGainPolicy,
    QuestionPolicy,
    RandomPolicy,
)
from src.diagnosis.service import DiagnosisService  # noqa: E402


def run_case(
    service: DiagnosisService,
    case: dict,
    policy: QuestionPolicy | None = None,
) -> dict:
    """运行单条完整诊断路径；默认使用系统的信息增益策略。"""
    policy = policy or InformationGainPolicy()
    snapshot = service.start(case["report"])
    initial_entropy = service.engine.entropy(DiagnosisState.from_dict(snapshot["state"]))

    while snapshot["state"]["status"] == "questioning":
        state = DiagnosisState.from_dict(snapshot["state"])
        question = policy.choose(service.engine, state)
        if question is None:
            snapshot = service.complete(snapshot["state"])
            break
        answer = case["answers"].get(question.name, "unknown")
        snapshot = service.answer(snapshot["state"], question.name, answer)

    candidates = snapshot["candidates"]
    expected = case["expected_top_cause"]
    rank = next(
        (index for index, item in enumerate(candidates, start=1) if item["name"] == expected),
        len(candidates) + 1,
    )
    predicted = candidates[0]
    questions = len(snapshot["state"]["asked_questions"])
    final_entropy = service.engine.entropy(DiagnosisState.from_dict(snapshot["state"]))
    passed = predicted["name"] == expected
    return {
        "id": case["id"],
        "split": case.get("split", "unspecified"),
        "expected": expected,
        "predicted": predicted["name"],
        "probability": predicted["probability"],
        "rank": rank,
        "reciprocal_rank": 1 / rank,
        "questions": questions,
        "success_within_3": passed and questions <= 3,
        "entropy_drop": initial_entropy - final_entropy,
        "passed": passed,
    }


def summarize(strategy: str, results: list[dict]) -> dict:
    total = len(results)
    return {
        "strategy": strategy,
        "trajectories": total,
        "top1": sum(item["passed"] for item in results) / total,
        "mrr": sum(item["reciprocal_rank"] for item in results) / total,
        "avg_questions": sum(item["questions"] for item in results) / total,
        "success_within_3": sum(item["success_within_3"] for item in results) / total,
        "avg_entropy_drop": sum(item["entropy_drop"] for item in results) / total,
    }


def evaluate(cases: list[dict], random_runs: int = 100, seed: int = 2026) -> dict:
    service = DiagnosisService()
    policies: list[QuestionPolicy] = [
        DirectPolicy(),
        FixedOrderPolicy(),
        InformationGainPolicy(),
    ]
    details: dict[str, list[dict]] = {}
    summaries: list[dict] = []

    for policy in policies:
        results = [run_case(service, case, policy) for case in cases]
        details[policy.name] = results
        summaries.append(summarize(policy.name, results))

    random_results: list[dict] = []
    random_by_case: dict[str, list[dict]] = defaultdict(list)
    for run_index in range(random_runs):
        policy = RandomPolicy(seed + run_index)
        for case in cases:
            result = run_case(service, case, policy)
            random_results.append(result)
            random_by_case[case["id"]].append(result)
    details["random_question"] = [
        {
            "id": case_id,
            "runs": len(items),
            **summarize("random_question", items),
        }
        for case_id, items in random_by_case.items()
    ]
    summaries.insert(2, summarize("random_question", random_results))

    return {
        "benchmark": "data/evaluation/diagnosis_cases.json",
        "case_count": len(cases),
        "random_runs": random_runs,
        "random_seed": seed,
        "metrics": summaries,
        "details": details,
    }


def print_table(report: dict) -> None:
    print("策略                 Top-1    MRR    平均追问  3问内成功  平均熵下降")
    print("-" * 72)
    for item in report["metrics"]:
        print(
            f"{item['strategy']:<20} "
            f"{item['top1']:>6.1%} "
            f"{item['mrr']:>6.3f} "
            f"{item['avg_questions']:>9.2f} "
            f"{item['success_within_3']:>9.1%} "
            f"{item['avg_entropy_drop']:>10.3f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--random-runs", type=int, default=100)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--json", type=Path, help="同时把完整结果写入 JSON 文件")
    args = parser.parse_args()
    if args.random_runs < 1:
        parser.error("--random-runs 必须大于 0")

    cases = json.loads(
        (ROOT / "data/evaluation/diagnosis_cases.json").read_text(encoding="utf-8")
    )
    report = evaluate(cases, random_runs=args.random_runs, seed=args.seed)
    print_table(report)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\n完整结果已写入 {args.json}")


if __name__ == "__main__":
    main()
