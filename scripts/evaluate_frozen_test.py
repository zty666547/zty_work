#!/usr/bin/env python3
"""只对已封存的未见案例执行一次正式模型评测。"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import Settings  # noqa: E402
from scripts.audit_model_freeze import build_report as audit_model  # noqa: E402
from scripts.evaluate_active_algorithm import run_case, summarize  # noqa: E402
from scripts.seal_frozen_test import build_seal  # noqa: E402
from src.diagnosis.service import DiagnosisService  # noqa: E402

CASES_PATH = ROOT / "data/evaluation/public_cases.json"
SPLIT_PATH = ROOT / "data/evaluation/real_case_split.json"
SEAL_PATH = ROOT / "data/evaluation/frozen_test_seal.json"
OUTPUT_PATH = ROOT / "data/evaluation/frozen_test_results.json"


def prepare_evaluation() -> tuple[list[dict], dict, dict]:
    """核验双重指纹，并按封存顺序返回测试案例。"""
    model = audit_model()
    if not model["frozen"]:
        raise ValueError(f"模型冻结校验失败：{model['mismatches']}")
    saved_seal = json.loads(SEAL_PATH.read_text(encoding="utf-8"))
    current_seal = build_seal()
    if saved_seal != current_seal:
        raise ValueError("测试集封存校验失败，禁止运行正式评测")

    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    by_id = {case["id"]: case for case in cases}
    split = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
    selected = [by_id[case_id] for case_id in split["frozen_test_ids"]]
    if [case["id"] for case in selected] != saved_seal["case_ids"]:
        raise ValueError("冻结测试案例顺序与封存清单不一致")
    return selected, model, saved_seal


def evaluate_once() -> dict:
    if OUTPUT_PATH.exists():
        raise FileExistsError("正式评测结果已存在；协议禁止重复运行或覆盖")
    cases, model, seal = prepare_evaluation()
    service = DiagnosisService(Settings())
    rows = [run_case(service, case, unknown_below=0.0) for case in cases]
    metric = summarize("frozen_answerability_aware", rows)
    return {
        "benchmark": "sealed_unseen_real_case_test_v1",
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_freeze_id": model["freeze_id"],
        "test_seal_id": seal["seal_id"],
        "test_content_sha256": seal["content_sha256"],
        "case_count": len(cases),
        "cause_count": seal["cause_count"],
        "missing_answers_policy": "unknown",
        "metric": metric,
        "details": rows,
        "scope": "14条公开确认案例的一次性未见测试；样本量较小，不代表真实世界总体准确率。",
    }


def print_result(report: dict) -> None:
    metric = report["metric"]
    print(f"冻结测试集：{report['case_count']}条，覆盖{report['cause_count']}类根因")
    print(
        f"Top-1={metric['top1']:.1%}；覆盖率={metric['coverage']:.1%}；"
        f"平均追问={metric['avg_questions']:.2f}；"
        f"错误自信停止={metric['wrong_confident_stop_rate']:.1%}"
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
