#!/usr/bin/env python3
"""只对已封存的未见案例执行一次正式模型评测。"""
from __future__ import annotations

import json
import hashlib
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import Settings  # noqa: E402
from scripts.audit_model_freeze import build_report as audit_model  # noqa: E402
from scripts.seal_frozen_test import build_seal  # noqa: E402
from src.diagnosis.engine import UnknownIssueError  # noqa: E402
from src.diagnosis.models import DiagnosisState  # noqa: E402
from src.diagnosis.policies import (  # noqa: E402
    DirectPolicy,
    FixedOrderPolicy,
    InformationGainPolicy,
    PureInformationGainPolicy,
    QuestionPolicy,
    RandomPolicy,
)
from src.diagnosis.service import DiagnosisService  # noqa: E402

CASES_PATH = ROOT / "data/evaluation/public_cases.json"
SPLIT_PATH = ROOT / "data/evaluation/real_case_split.json"
SEAL_PATH = ROOT / "data/evaluation/frozen_test_seal.json"
PROTOCOL_PATH = ROOT / "data/evaluation/frozen_evaluation_protocol.json"
OUTPUT_PATH = ROOT / "data/evaluation/frozen_test_results.json"


def load_protocol() -> dict:
    """读取并核对评测协议自身的内容指纹。"""
    document = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    canonical = json.dumps(
        document["protocol"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    actual = hashlib.sha256(canonical).hexdigest()
    if actual != document["content_sha256"]:
        raise ValueError("正式评测协议指纹不一致，禁止运行")
    return document


def prepare_evaluation() -> tuple[list[dict], dict, dict, dict]:
    """核验模型、测试集和协议三重指纹，并返回封存案例。"""
    model = audit_model()
    if not model["frozen"]:
        raise ValueError(f"模型冻结校验失败：{model['mismatches']}")
    saved_seal = json.loads(SEAL_PATH.read_text(encoding="utf-8"))
    current_seal = build_seal()
    if saved_seal != current_seal:
        raise ValueError("测试集封存校验失败，禁止运行正式评测")
    protocol = load_protocol()
    rules = protocol["protocol"]
    if rules["model_freeze_id"] != model["freeze_id"]:
        raise ValueError("协议引用的模型冻结版本不一致")
    if rules["test_seal_id"] != saved_seal["seal_id"]:
        raise ValueError("协议引用的测试集封存版本不一致")
    if rules["test_content_sha256"] != saved_seal["content_sha256"]:
        raise ValueError("协议引用的测试集指纹不一致")

    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    by_id = {case["id"]: case for case in cases}
    split = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
    selected = [by_id[case_id] for case_id in split["frozen_test_ids"]]
    if [case["id"] for case in selected] != saved_seal["case_ids"]:
        raise ValueError("冻结测试案例顺序与封存清单不一致")
    if len(selected) != rules["case_count"]:
        raise ValueError("协议案例数量与冻结测试集不一致")
    return selected, model, saved_seal, protocol


def run_strategy_case(
    service: DiagnosisService,
    case: dict,
    policy: QuestionPolicy,
) -> dict:
    """在相同检索、答案和停止条件下运行一条策略轨迹。"""
    try:
        snapshot = service.start(case["report"])
    except UnknownIssueError as exc:
        return {
            "id": case["id"],
            "family": case["family"],
            "expected": case["expected_top_cause"],
            "predicted": None,
            "probability": 0.0,
            "rank": None,
            "reciprocal_rank": 0.0,
            "passed": False,
            "decision_sufficient": False,
            "resolved_correctly": False,
            "questions": 0,
            "unknown_questions": 0,
            "success_within_3": False,
            "entropy_drop": 0.0,
            "total_cost": 0.0,
            "total_risk": 0.0,
            "stop_reason": "故障族识别失败",
            "wrong_confident_stop": False,
            "entry_error": str(exc),
        }
    initial_entropy = service.engine.entropy(
        DiagnosisState.from_dict(snapshot["state"])
    )
    unknown_questions = 0
    total_cost = 0.0
    total_risk = 0.0

    while snapshot["state"]["status"] == "questioning":
        state = DiagnosisState.from_dict(snapshot["state"])
        question = policy.choose(service.engine, state)
        if question is None:
            snapshot = service.complete(snapshot["state"])
            break
        answer = case["answers"].get(question.name, "unknown")
        unknown_questions += answer == "unknown"
        total_cost += question.cost
        total_risk += question.risk_cost
        snapshot = service.answer(snapshot["state"], question.name, answer)

    expected = case["expected_top_cause"]
    candidates = snapshot["candidates"]
    predicted = candidates[0]
    rank = next(
        (
            index
            for index, item in enumerate(candidates, start=1)
            if item["name"] == expected
        ),
        None,
    )
    passed = predicted["name"] == expected
    questions = len(snapshot["state"]["asked_questions"])
    final_entropy = service.engine.entropy(
        DiagnosisState.from_dict(snapshot["state"])
    )
    stop_reason = snapshot["state"]["stop_reason"]
    sufficient = snapshot["decision"]["sufficient"]
    return {
        "id": case["id"],
        "family": case["family"],
        "expected": expected,
        "predicted": predicted["name"],
        "probability": predicted["probability"],
        "rank": rank,
        "reciprocal_rank": 1 / rank if rank else 0.0,
        "passed": passed,
        "decision_sufficient": sufficient,
        "resolved_correctly": sufficient and passed,
        "questions": questions,
        "unknown_questions": unknown_questions,
        "success_within_3": passed and questions <= 3,
        "entropy_drop": initial_entropy - final_entropy,
        "total_cost": total_cost,
        "total_risk": total_risk,
        "stop_reason": stop_reason,
        "wrong_confident_stop": not passed and "置信" in stop_reason,
        "entry_error": None,
    }


def summarize_strategy(
    strategy: str,
    rows: list[dict],
    case_count: int,
) -> dict:
    total = len(rows)
    resolved = [row for row in rows if row["decision_sufficient"]]
    return {
        "strategy": strategy,
        "cases": case_count,
        "trajectories": total,
        "top1": sum(row["passed"] for row in rows) / total,
        "mrr": sum(row["reciprocal_rank"] for row in rows) / total,
        "coverage": len(resolved) / total,
        "selective_accuracy": (
            sum(row["passed"] for row in resolved) / len(resolved)
            if resolved
            else None
        ),
        "avg_questions": sum(row["questions"] for row in rows) / total,
        "avg_unknown_questions": sum(row["unknown_questions"] for row in rows) / total,
        "success_within_3": sum(row["success_within_3"] for row in rows) / total,
        "avg_entropy_drop": sum(row["entropy_drop"] for row in rows) / total,
        "avg_cost": sum(row["total_cost"] for row in rows) / total,
        "avg_risk": sum(row["total_risk"] for row in rows) / total,
        "wrong_confident_stop_rate": (
            sum(row["wrong_confident_stop"] for row in rows) / total
        ),
        "entry_failure_rate": sum(row["entry_error"] is not None for row in rows) / total,
    }


def evaluate_once() -> dict:
    if OUTPUT_PATH.exists():
        raise FileExistsError("正式评测结果已存在；协议禁止重复运行或覆盖")
    cases, model, seal, protocol = prepare_evaluation()
    rules = protocol["protocol"]
    strategies = [
        ("direct_no_question", DirectPolicy()),
        ("fixed_order", FixedOrderPolicy()),
        ("pure_information_gain", PureInformationGainPolicy()),
        ("full_answerability_aware", InformationGainPolicy()),
    ]
    details: dict[str, list[dict]] = {}
    metrics: list[dict] = []
    for name, policy in strategies:
        service = DiagnosisService(Settings())
        rows = [run_strategy_case(service, case, policy) for case in cases]
        details[name] = rows
        metrics.append(summarize_strategy(name, rows, len(cases)))

    random_rows: list[dict] = []
    random_by_case: dict[str, list[dict]] = defaultdict(list)
    random_rules = rules["random"]
    random_service = DiagnosisService(Settings())
    for run_index in range(random_rules["runs"]):
        policy = RandomPolicy(random_rules["seed"] + run_index)
        for case in cases:
            row = run_strategy_case(random_service, case, policy)
            random_rows.append(row)
            random_by_case[case["id"]].append(row)
    details["random_question"] = [
        {
            "id": case_id,
            "runs": len(rows),
            "metric": summarize_strategy("random_question", rows, 1),
        }
        for case_id, rows in random_by_case.items()
    ]
    random_metric = summarize_strategy("random_question", random_rows, len(cases))
    metrics.insert(2, random_metric)

    expected_order = [item["id"] for item in rules["strategies"]]
    if [item["strategy"] for item in metrics] != expected_order:
        raise ValueError("实际策略顺序与封存评测协议不一致")
    return {
        "benchmark": "sealed_unseen_real_case_comparison_v1",
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_freeze_id": model["freeze_id"],
        "test_seal_id": seal["seal_id"],
        "test_content_sha256": seal["content_sha256"],
        "evaluation_protocol_id": protocol["protocol_id"],
        "evaluation_protocol_sha256": protocol["content_sha256"],
        "case_count": len(cases),
        "cause_count": seal["cause_count"],
        "random_runs": random_rules["runs"],
        "random_seed": random_rules["seed"],
        "entry_failures": sum(
            row["entry_error"] is not None for row in details["direct_no_question"]
        ),
        "metrics": metrics,
        "details": details,
        "scope": "14条公开确认案例的一次性未见对比测试；每类原因1条，样本量较小，不代表真实世界总体准确率。",
    }


def print_result(report: dict) -> None:
    print(f"冻结测试集：{report['case_count']}条，覆盖{report['cause_count']}类根因")
    print(f"其中故障族识别失败：{report['entry_failures']}条（按端到端失败计入全部策略）")
    print("策略                         Top-1   覆盖率  平均追问  不清楚  错误自信停止")
    print("-" * 84)
    for metric in report["metrics"]:
        print(
            f"{metric['strategy']:<28} {metric['top1']:>6.1%} "
            f"{metric['coverage']:>7.1%} {metric['avg_questions']:>9.2f} "
            f"{metric['avg_unknown_questions']:>7.2f} "
            f"{metric['wrong_confident_stop_rate']:>12.1%}"
        )
    print(report["scope"])


def main() -> None:
    if OUTPUT_PATH.exists():
        saved = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        print("正式评测已经执行，以下为首次封存结果；本次没有重新运行。")
        print_result(saved)
        return
    report = evaluate_once()
    with OUTPUT_PATH.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print("首次正式评测完成，结果已封存。")
    print_result(report)


if __name__ == "__main__":
    main()
