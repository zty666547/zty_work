#!/usr/bin/env python3
"""评估第二版故障族路由；结果仅用于开发，不是新的无偏测试。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import Settings  # noqa: E402
from src.data.loader import load_knowledge_base  # noqa: E402
from src.retrieval.issue_router import IssueRouter  # noqa: E402

CASES_PATH = ROOT / "data/evaluation/public_cases.json"
SPLIT_PATH = ROOT / "data/evaluation/real_case_split.json"
OUTPUT_PATH = ROOT / "data/evaluation/v2_router_development_results.json"

FAMILY_TO_ISSUE = {
    "python_import": "Python模块无法导入",
    "pytorch_gpu": "PyTorch无法使用GPU",
    "service_config": "服务或配置连接失败",
}


def evaluate() -> dict:
    settings = Settings()
    graph_path = settings.raw_dir / settings.structured_filename
    evidence_path = settings.raw_dir / settings.evidence_filename
    graph = load_knowledge_base(graph_path, evidence_path)
    router = IssueRouter(graph)
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    split = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
    by_id = {case["id"]: case for case in cases}

    cohorts = {
        "original_development": split["development_ids"],
        "visible_frozen_feedback": split["frozen_test_ids"],
    }
    summaries = []
    details = []
    for cohort, case_ids in cohorts.items():
        correct = 0
        for case_id in case_ids:
            case = by_id[case_id]
            expected = FAMILY_TO_ISSUE[case["family"]]
            candidates = router.candidates(case["report"])
            predicted = candidates[0]["issue"] if candidates else None
            passed = predicted == expected
            correct += passed
            details.append(
                {
                    "id": case_id,
                    "cohort": cohort,
                    "expected": expected,
                    "predicted": predicted,
                    "passed": passed,
                    "candidates": candidates,
                }
            )
        summaries.append(
            {
                "cohort": cohort,
                "cases": len(case_ids),
                "top1": correct / len(case_ids) if case_ids else None,
            }
        )

    return {
        "benchmark": "debugpath-v2-issue-router-development-v1",
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "warning": "本结果包含已经查看的首次冻结案例，只能用于第二版开发，不能作为新的无偏测试成绩。",
        "method": "55%固定特征匹配 + 45%证据BM25聚合；无固定特征时由证据检索独立路由。",
        "summaries": summaries,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = evaluate()
    for item in report["summaries"]:
        print(f"{item['cohort']}: {item['cases']}条，Top-1={item['top1']:.1%}")
    print(report["warning"])
    if args.write:
        OUTPUT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"已写入：{OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
