#!/usr/bin/env python3
"""比较文本证据、图谱先验和主动询问的贡献。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import Settings  # noqa: E402
from scripts.evaluate_diagnosis import load_cases, run_case, summarize  # noqa: E402
from src.diagnosis.policies import DirectPolicy, InformationGainPolicy  # noqa: E402
from src.diagnosis.service import DiagnosisService  # noqa: E402


def evaluate_ablation(cases: list[dict]) -> dict:
    methods = [
        (
            "graph_prior_only",
            DiagnosisService(Settings(enable_evidence_retrieval=False)),
            DirectPolicy(),
        ),
        (
            "text_evidence_only",
            DiagnosisService(Settings(evidence_weight=1.0)),
            DirectPolicy(),
        ),
        ("hybrid_no_question", DiagnosisService(Settings()), DirectPolicy()),
        (
            "graph_active",
            DiagnosisService(Settings(enable_evidence_retrieval=False)),
            InformationGainPolicy(),
        ),
        ("hybrid_active", DiagnosisService(Settings()), InformationGainPolicy()),
    ]
    details: dict[str, list[dict]] = {}
    metrics: list[dict] = []
    for name, service, policy in methods:
        results = [run_case(service, case, policy) for case in cases]
        details[name] = results
        metrics.append(summarize(name, results))
    return {"case_count": len(cases), "metrics": metrics, "details": details}


def main() -> None:
    report = evaluate_ablation(load_cases())
    print("方法                    Top-1    MRR    平均追问  3问内成功")
    print("-" * 67)
    for item in report["metrics"]:
        print(
            f"{item['strategy']:<23} {item['top1']:>6.1%} {item['mrr']:>6.3f} "
            f"{item['avg_questions']:>9.2f} {item['success_within_3']:>9.1%}"
        )
    output = ROOT / "data/evaluation/ablation_results.json"
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\n完整结果已写入 {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
