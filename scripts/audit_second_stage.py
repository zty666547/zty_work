#!/usr/bin/env python3
"""审计14个候选根因的图谱结构与真实案例缺口。"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.diagnosis.service import DiagnosisService  # noqa: E402

CASES_PATH = ROOT / "data/evaluation/public_cases.json"
OUTPUT_PATH = ROOT / "data/evaluation/second_stage_gap_report.json"
TARGET_CONFIRMED_PER_CAUSE = 2


def _targets_by_source(service: DiagnosisService, relation_type: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for relation in service.graph.relations:
        if relation["type"] == relation_type:
            result[relation["source"]].append(relation["target"])
    return result


def build_report() -> dict:
    service = DiagnosisService()
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    confirmed = Counter(
        case["expected_top_cause"]
        for case in payload["cases"]
        if case["root_cause_status"] == "confirmed"
    )
    unconfirmed = Counter(
        cause
        for case in payload["cases"]
        if case["root_cause_status"] == "unconfirmed"
        for cause in case.get("candidate_causes", [])
    )

    checks = _targets_by_source(service, "CAUSE_CHECKED_BY")
    repairs = _targets_by_source(service, "CAUSE_RESOLVED_BY")
    sources = _targets_by_source(service, "CAUSE_SUPPORTED_BY")
    platforms = _targets_by_source(service, "VALID_ON")
    versions = _targets_by_source(service, "SUBJECT_TO_VERSION")
    evidence = _targets_by_source(service, "CHUNK_SUPPORTS_CAUSE")
    observations: dict[str, list[str]] = defaultdict(list)
    for relation in service.graph.relations:
        if relation["type"] == "OBSERVATION_SUPPORTS":
            observations[relation["target"]].append(relation["source"])

    rows = []
    for issue, causes in service.engine.issue_causes.items():
        for cause in causes:
            name = cause["name"]
            rows.append(
                {
                    "issue": issue,
                    "cause": name,
                    "graph": {
                        "observations": len(observations[name]),
                        "checks": len(checks[name]),
                        "repairs": len(repairs[name]),
                        "direct_sources": len(sources[name]),
                        "evidence_chunks": len(evidence[name]),
                        "platform_constraints": len(platforms[name]),
                        "version_constraints": len(versions[name]),
                    },
                    "cases": {
                        "confirmed": confirmed[name],
                        "unconfirmed_mentions": unconfirmed[name],
                        "target_confirmed": TARGET_CONFIRMED_PER_CAUSE,
                        "confirmed_gap": max(
                            0, TARGET_CONFIRMED_PER_CAUSE - confirmed[name]
                        ),
                    },
                }
            )

    structural_gaps = [
        row["cause"]
        for row in rows
        if any(
            row["graph"][field] == 0
            for field in ("observations", "checks", "repairs", "direct_sources")
        )
    ]
    return {
        "target": {
            "confirmed_cases_per_cause": TARGET_CONFIRMED_PER_CAUSE,
            "total_causes": len(rows),
            "target_confirmed_cases": len(rows) * TARGET_CONFIRMED_PER_CAUSE,
        },
        "summary": {
            "confirmed_cases": sum(confirmed.values()),
            "confirmed_case_gap": sum(row["cases"]["confirmed_gap"] for row in rows),
            "causes_with_confirmed_case": sum(
                row["cases"]["confirmed"] > 0 for row in rows
            ),
            "structural_gap_causes": structural_gaps,
        },
        "causes": rows,
        "interpretation": (
            "结构完整只表示原因具有观察、检查、修复和来源；"
            "真实案例数量才用于估计参数和独立评测。"
        ),
    }


def main() -> None:
    report = build_report()
    OUTPUT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = report["summary"]
    print(
        f"候选根因：{report['target']['total_causes']}；"
        f"已有确认案例：{summary['confirmed_cases']}；"
        f"仍缺：{summary['confirmed_case_gap']}"
    )
    print(f"存在确认案例的原因：{summary['causes_with_confirmed_case']}/14")
    print(
        "图谱结构缺口："
        + ("、".join(summary["structural_gap_causes"]) or "无")
    )


if __name__ == "__main__":
    main()
