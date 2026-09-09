#!/usr/bin/env python3
"""比较原始信息增益与可回答性感知主动诊断算法。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import Settings  # noqa: E402
from scripts.evaluate_diagnosis import load_cases  # noqa: E402
from src.diagnosis.service import DiagnosisService  # noqa: E402


def run_case(
    service: DiagnosisService,
    case: dict,
    unknown_below: float,
) -> dict:
    """模拟信息受限用户：低于阈值的问题统一回答 unknown。"""
    snapshot = service.start(case["report"])
    unknown_questions = 0
    total_cost = 0.0
    total_risk = 0.0

    while snapshot["state"]["status"] == "questioning":
        question = snapshot["question"]
        if question is None:
            snapshot = service.complete(snapshot["state"])
            break
        total_cost += question["cost"]
        total_risk += question["risk_cost"]
        if question["answerability"] < unknown_below:
            answer = "unknown"
            unknown_questions += 1
        else:
            answer = case["answers"].get(question["name"], "unknown")
            unknown_questions += answer == "unknown"
        snapshot = service.answer(snapshot["state"], question["name"], answer)

    expected = case["expected_top_cause"]
    predicted = snapshot["candidates"][0]
    return {
        "id": case["id"],
        "split": case["split"],
        "expected": expected,
        "predicted": predicted["name"],
        "probability": predicted["probability"],
        "passed": predicted["name"] == expected,
        "questions": len(snapshot["state"]["asked_questions"]),
        "unknown_questions": unknown_questions,
        "total_cost": total_cost,
        "total_risk": total_risk,
        "stop_reason": snapshot["state"]["stop_reason"],
    }


def summarize(name: str, rows: list[dict]) -> dict:
    total = len(rows)
    wrong_confident_stops = sum(
        not row["passed"] and "置信" in row["stop_reason"] for row in rows
    )
    return {
        "algorithm": name,
        "cases": total,
        "top1": sum(row["passed"] for row in rows) / total,
        "avg_questions": sum(row["questions"] for row in rows) / total,
        "avg_unknown_questions": sum(row["unknown_questions"] for row in rows) / total,
        "avg_cost": sum(row["total_cost"] for row in rows) / total,
        "avg_risk": sum(row["total_risk"] for row in rows) / total,
        "wrong_confident_stop_rate": wrong_confident_stops / total,
    }


def evaluate(cases: list[dict], unknown_below: float = 0.8) -> dict:
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
        name: [run_case(service, case, unknown_below) for case in cases]
        for name, service in algorithms
    }
    return {
        "benchmark": "information_limited_user_stress_test",
        "case_count": len(cases),
        "unknown_below_answerability": unknown_below,
        "note": "低可回答率问题被确定性模拟为unknown；该压力测试不等同于真实用户准确率。",
        "metrics": [summarize(name, details[name]) for name, _ in algorithms],
        "details": details,
    }


def print_table(report: dict) -> None:
    print("算法                         Top-1  平均追问  无法回答  检查成本  错误自信停止")
    print("-" * 82)
    for row in report["metrics"]:
        print(
            f"{row['algorithm']:<28} {row['top1']:>6.1%} "
            f"{row['avg_questions']:>9.2f} {row['avg_unknown_questions']:>9.2f} "
            f"{row['avg_cost']:>9.2f} {row['wrong_confident_stop_rate']:>11.1%}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unknown-below", type=float, default=0.8)
    parser.add_argument(
        "--json",
        type=Path,
        default=ROOT / "data/evaluation/active_algorithm_results.json",
    )
    args = parser.parse_args()
    if not 0 <= args.unknown_below <= 1:
        parser.error("--unknown-below 必须位于0到1之间")

    report = evaluate(load_cases(), args.unknown_below)
    print_table(report)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        display_path = args.json.relative_to(ROOT)
    except ValueError:
        display_path = args.json
    print(f"\n完整结果已写入 {display_path}")


if __name__ == "__main__":
    main()
