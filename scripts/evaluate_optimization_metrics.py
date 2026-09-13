#!/usr/bin/env python3
"""对既有确认案例执行图谱优化的事后消融分析。

该脚本按案例已知故障族启动诊断，只评估条件概率校准与新增问题；
冻结测试案例此前已经被查看，因此输出不得解释为新的独立测试结果。
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.diagnosis.service_v2 import DiagnosisServiceV2  # noqa: E402

CASES_PATH = ROOT / "data/evaluation/public_cases.json"
SPLIT_PATH = ROOT / "data/evaluation/real_case_split.json"
OUTPUT_PATH = ROOT / "data/evaluation/optimization_metrics_exploratory.json"
TARGETED_CASES_PATH = ROOT / "data/evaluation/targeted_validation_cases.json"

HOST_QUESTION = "Q-目标主机本机检查是否成功"
HOST_OBSERVATION = "O-目标主机本机检查成功"
PACKAGE_OBSERVATION = "O-当前环境可见目标包"
VERSION_CAUSE = "Python版本与包不兼容"
SERVICE_ISSUE = "服务或配置连接失败"

FAMILY_TO_ISSUE = {
    "python_import": "Python模块无法导入",
    "pytorch_gpu": "PyTorch无法使用GPU",
    "service_config": SERVICE_ISSUE,
}


def load_cases(split_name: str) -> list[dict]:
    if split_name == "targeted_validation":
        return json.loads(TARGETED_CASES_PATH.read_text(encoding="utf-8"))["cases"]
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    split = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
    ids = set(split[f"{split_name}_ids"])
    return [case for case in payload["cases"] if case["id"] in ids]


def build_service(*, recalibrate_package: bool, add_host_question: bool) -> DiagnosisServiceV2:
    service = DiagnosisServiceV2()
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


def start_in_known_family(service: DiagnosisServiceV2, case: dict) -> dict:
    issue = FAMILY_TO_ISSUE[case["family"]]
    routing = {
        "status": "evaluation_oracle_family",
        "selected_issue": issue,
        "candidates": [{"issue": issue}],
        "clarification": None,
    }
    return service._start_routed(case["report"], routing)


def multiclass_brier(candidates: list[dict], expected: str) -> float:
    return sum(
        (float(item["probability"]) - (1.0 if item["name"] == expected else 0.0)) ** 2
        for item in candidates
    )


def run_case(service: DiagnosisServiceV2, case: dict) -> dict:
    snapshot = start_in_known_family(service, case)
    initial_candidates = snapshot["candidates"]
    initial_expected_probability = next(
        item["probability"] for item in initial_candidates if item["name"] == case["expected_top_cause"]
    )

    while snapshot["state"]["status"] == "questioning":
        question = snapshot["question"]
        if question is None:
            snapshot = service.complete(snapshot["state"])
            break
        answer = case["answers"].get(question["name"], "unknown")
        snapshot = service.answer(snapshot["state"], question["name"], answer)

    expected = case["expected_top_cause"]
    candidates = snapshot["candidates"]
    rank = next(index for index, item in enumerate(candidates, start=1) if item["name"] == expected)
    expected_probability = next(item["probability"] for item in candidates if item["name"] == expected)
    best_other = max(item["probability"] for item in candidates if item["name"] != expected)
    questions = len(snapshot["state"]["asked_questions"])
    passed = rank == 1
    sufficient = bool(snapshot["decision"]["sufficient"])
    return {
        "id": case["id"],
        "family": case["family"],
        "expected": expected,
        "predicted": candidates[0]["name"],
        "rank": rank,
        "reciprocal_rank": 1.0 / rank,
        "passed": passed,
        "decision_sufficient": sufficient,
        "resolved_correctly": sufficient and passed,
        "questions": questions,
        "success_within_3": sufficient and passed and questions <= 3,
        "initial_expected_probability": initial_expected_probability,
        "expected_probability": expected_probability,
        "target_margin": expected_probability - best_other,
        "brier": multiclass_brier(candidates, expected),
        "log_loss": -math.log(max(expected_probability, 1e-12)),
        "stop_reason": snapshot["state"]["stop_reason"],
        "asked_questions": snapshot["state"]["asked_questions"],
        "answers": snapshot["state"]["answers"],
    }


def summarize(rows: list[dict]) -> dict:
    return {
        "cases": len(rows),
        "top1": statistics.fmean(row["passed"] for row in rows),
        "mrr_at_5": statistics.fmean(row["reciprocal_rank"] for row in rows),
        "brier": statistics.fmean(row["brier"] for row in rows),
        "log_loss": statistics.fmean(row["log_loss"] for row in rows),
        "avg_target_probability": statistics.fmean(row["expected_probability"] for row in rows),
        "avg_target_margin": statistics.fmean(row["target_margin"] for row in rows),
        "coverage": statistics.fmean(row["decision_sufficient"] for row in rows),
        "resolved_accuracy": statistics.fmean(row["resolved_correctly"] for row in rows),
        "avg_questions": statistics.fmean(row["questions"] for row in rows),
        "median_questions": statistics.median(row["questions"] for row in rows),
        "success_within_3": statistics.fmean(row["success_within_3"] for row in rows),
    }


def evaluate() -> dict:
    variants = [
        ("original", False, False),
        ("likelihood_only", True, False),
        ("new_question_only", False, True),
        ("combined", True, True),
    ]
    cohorts = {
        "development": load_cases("development"),
        "previously_viewed_frozen": load_cases("frozen_test"),
        "targeted_validation": load_cases("targeted_validation"),
    }
    details: dict[str, dict[str, list[dict]]] = {}
    summaries: dict[str, dict[str, dict]] = {}
    for cohort_name, cases in cohorts.items():
        details[cohort_name] = {}
        summaries[cohort_name] = {}
        for variant, likelihood, question in variants:
            rows = [
                run_case(
                    build_service(
                        recalibrate_package=likelihood,
                        add_host_question=question,
                    ),
                    case,
                )
                for case in cases
            ]
            details[cohort_name][variant] = rows
            summaries[cohort_name][variant] = summarize(rows)

    return {
        "benchmark": "debugpath_graph_optimization_posthoc_ablation_v1",
        "variants": [variant for variant, _, _ in variants],
        "evaluation_mode": "oracle_issue_family",
        "metric_definitions": {
            "mrr_at_5": "正确原因排名倒数的平均值；每个故障族最多5个候选原因",
            "brier": "多分类Brier分数，越低越好；只衡量当前候选原因分布",
            "success_within_3": "正确且满足置信停止条件，并在3个诊断问题内结束",
            "target_margin": "正确原因概率减去最高竞争原因概率",
        },
        "warning": (
            "冻结案例已经在此前正式评测中被查看；本报告仅做事后机制分析，"
            "不得表述为新的未见测试，也不得据此继续调整参数。新增4例仅用于"
            "验证两项已固定优化的目标机制，不代表总体准确率。"
        ),
        "summaries": summaries,
        "details": details,
    }


def main() -> None:
    report = evaluate()
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for cohort, variants in report["summaries"].items():
        print(f"\n{cohort}")
        print("版本                 Top-1   MRR@5   Brier   目标概率   平均问题   3问内完成")
        print("-" * 82)
        for name, row in variants.items():
            print(
                f"{name:<20} {row['top1']:>6.1%} {row['mrr_at_5']:>7.3f} "
                f"{row['brier']:>8.3f} {row['avg_target_probability']:>9.1%} "
                f"{row['avg_questions']:>10.2f} {row['success_within_3']:>10.1%}"
            )
    print(f"\n完整结果已写入 {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
