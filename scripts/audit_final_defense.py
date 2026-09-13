#!/usr/bin/env python3
"""生成并校验最终答辩使用的统一事实数据。"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.diagnosis.service_v2 import DiagnosisServiceV2  # noqa: E402

OUTPUT_PATH = ROOT / "data/evaluation/final_defense_evidence.json"


def _load(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def _assert_close(actual: float, expected: float) -> None:
    if not math.isclose(actual, expected, rel_tol=0, abs_tol=0.0005):
        raise AssertionError(f"数值不一致：actual={actual}, expected={expected}")


def build_report() -> dict:
    service = DiagnosisServiceV2()
    node_counts = {name: len(rows) for name, rows in service.graph.entities.items()}
    relation_types = sorted({row["type"] for row in service.graph.relations})

    trajectory = _load("data/demo/open_webui_ollama_trajectory.json")
    strategy = _load("data/evaluation/v2_strategy_development_results.json")
    frozen = _load("data/evaluation/frozen_test_results.json")
    injection = _load("data/evaluation/injection_results.json")
    public_cases = _load("data/evaluation/public_cases.json")

    stages = trajectory["trajectory"]
    top_probabilities = [stage["candidates"][0]["probability"] for stage in stages]
    entropies = [stage["entropy"] for stage in stages]

    split_counts = Counter(case["split"] for case in public_cases["cases"])
    status_counts = Counter(case["root_cause_status"] for case in public_cases["cases"])
    development = {
        (row["cohort"], row["strategy"]): row
        for row in strategy["summaries"]
    }
    frozen_metrics = {row["strategy"]: row for row in frozen["metrics"]}

    report = {
        "graph": {
            "nodes": sum(node_counts.values()),
            "relations": len(service.graph.relations),
            "node_types": len(node_counts),
            "relation_types": len(relation_types),
            "evidence_chunks": node_counts.get("EvidenceChunk", 0),
            "node_type_counts": node_counts,
        },
        "demo": {
            "scenario": trajectory["scenario"]["title"],
            "expected_cause": trajectory["scenario"]["expected_cause"],
            "stage_count": len(stages),
            "top_probabilities": top_probabilities,
            "entropies": entropies,
            "first_question": stages[0]["next_question"]["text"],
            "first_question_information_gain": stages[0]["next_question"]["information_gain"],
            "first_question_answerability": stages[0]["next_question"]["answerability"],
            "first_question_utility": stages[0]["next_question"]["utility"],
            "stop_reason": stages[-1]["stop_reason"],
        },
        "development_behavior": {
            "reviewed_confirmed_cases": status_counts["confirmed"],
            "changed_first_questions": strategy["initial_question_difference_count"],
            "original_development_pure_top1": development[
                ("original_development", "pure_information_gain")
            ]["top1"],
            "original_development_full_top1": development[
                ("original_development", "answerability_aware")
            ]["top1"],
            "claim_boundary": strategy["warning"],
        },
        "first_frozen_test": {
            "cases": frozen["case_count"],
            "entry_failures": frozen["entry_failures"],
            "top1": {
                name: frozen_metrics[name]["top1"]
                for name in (
                    "direct_no_question",
                    "fixed_order",
                    "random_question",
                    "pure_information_gain",
                    "full_answerability_aware",
                )
            },
            "claim_boundary": frozen["scope"],
        },
        "knowledge_injection": {
            "valid_cases": injection["valid_cases"],
            "invalid_cases": injection["invalid_cases"],
            "valid_acceptance_rate": injection["valid_acceptance_rate"],
            "invalid_rejection_rate": injection["invalid_rejection_rate"],
            "claim_boundary": "只验证声明与证据白名单的程序边界，不等同于开放式大模型安全评测。",
        },
        "case_pool": {
            "development": split_counts["candidate"],
            "viewed_frozen_test": split_counts["frozen_test"],
            "unconfirmed": split_counts["unconfirmed"],
        },
    }

    assert report["graph"] | {
        "nodes": 147,
        "relations": 378,
        "node_types": 15,
        "relation_types": 27,
        "evidence_chunks": 33,
    } == report["graph"]
    assert len(stages) == 3
    for actual, expected in zip(top_probabilities, (0.56, 0.952272, 0.968854)):
        _assert_close(actual, expected)
    assert strategy["initial_question_difference_count"] == 15
    assert injection["valid_cases"] == 9
    assert injection["invalid_cases"] == 24
    assert split_counts == Counter(candidate=28, frozen_test=14, unconfirmed=3)
    return report


def main() -> None:
    report = build_report()
    OUTPUT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "最终答辩事实校验通过："
        f"图谱{report['graph']['nodes']}节点/{report['graph']['relations']}关系；"
        f"演示{report['demo']['stage_count']}阶段；"
        f"首问变化{report['development_behavior']['changed_first_questions']}条；"
        f"注入边界{report['knowledge_injection']['valid_cases']}条合法/"
        f"{report['knowledge_injection']['invalid_cases']}条非法。"
    )
    print(f"已写入：{OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
