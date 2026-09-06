#!/usr/bin/env python3
"""评估声明—证据白名单对合法与非法模型输出的处理。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.diagnosis.generator import (  # noqa: E402
    build_claim_manifest,
    validate_injection_decision,
)
from src.diagnosis.service import DiagnosisService  # noqa: E402


REPORTS = [
    "ModuleNotFoundError: No module named pandas",
    "macOS Apple Silicon上CUDA不可用",
    "Neo4j Connection refused",
]


def decisions_for(manifest: dict) -> tuple[list[dict], list[dict]]:
    claim_ids = [item["claim_id"] for item in manifest["claims"]]
    evidence_ids = [item["chunk_id"] for item in manifest["evidence"]]
    valid = [
        {
            "name": f"valid_{emphasis}",
            "decision": {
                "claim_order": claim_ids if emphasis == "diagnosis" else claim_ids[::-1],
                "evidence_ids": evidence_ids[:2],
                "emphasis": emphasis,
            },
        }
        for emphasis in ("diagnosis", "checks", "safety")
    ]
    invalid = [
        {
            "name": "unknown_claim",
            "decision": {
                "claim_order": ["C999"],
                "evidence_ids": [],
                "emphasis": "diagnosis",
            },
        },
        {
            "name": "missing_claim",
            "decision": {
                "claim_order": claim_ids[:-1],
                "evidence_ids": [],
                "emphasis": "checks",
            },
        },
        {
            "name": "duplicate_claim",
            "decision": {
                "claim_order": claim_ids + claim_ids[:1],
                "evidence_ids": [],
                "emphasis": "safety",
            },
        },
        {
            "name": "unknown_evidence",
            "decision": {
                "claim_order": claim_ids,
                "evidence_ids": ["E999"],
                "emphasis": "diagnosis",
            },
        },
        {
            "name": "duplicate_evidence",
            "decision": {
                "claim_order": claim_ids,
                "evidence_ids": evidence_ids[:1] * 2,
                "emphasis": "checks",
            },
        },
        {
            "name": "invalid_emphasis",
            "decision": {
                "claim_order": claim_ids,
                "evidence_ids": [],
                "emphasis": "execute",
            },
        },
        {"name": "free_text", "decision": {"answer": "sudo rm -rf /"}},
        {
            "name": "malformed_types",
            "decision": {
                "claim_order": [{"id": "C1"}],
                "evidence_ids": [{"id": "E001"}],
                "emphasis": "diagnosis",
            },
        },
    ]
    return valid, invalid


def evaluate() -> dict:
    service = DiagnosisService()
    details: list[dict] = []
    for report in REPORTS:
        snapshot = service.complete(service.start(report)["state"])
        manifest = build_claim_manifest(snapshot)
        valid, invalid = decisions_for(manifest)
        for expected_valid, cases in ((True, valid), (False, invalid)):
            for case in cases:
                errors = validate_injection_decision(case["decision"], manifest)
                accepted = not errors
                details.append(
                    {
                        "report": report,
                        "case": case["name"],
                        "expected_valid": expected_valid,
                        "accepted": accepted,
                        "passed": accepted == expected_valid,
                        "errors": errors,
                    }
                )
    valid_rows = [item for item in details if item["expected_valid"]]
    invalid_rows = [item for item in details if not item["expected_valid"]]
    return {
        "valid_cases": len(valid_rows),
        "invalid_cases": len(invalid_rows),
        "valid_acceptance_rate": sum(item["accepted"] for item in valid_rows)
        / len(valid_rows),
        "invalid_rejection_rate": sum(not item["accepted"] for item in invalid_rows)
        / len(invalid_rows),
        "false_acceptance_rate": sum(item["accepted"] for item in invalid_rows)
        / len(invalid_rows),
        "false_rejection_rate": sum(not item["accepted"] for item in valid_rows)
        / len(valid_rows),
        "details": details,
    }


def main() -> None:
    report = evaluate()
    print(
        f"合法编排：{report['valid_cases']}，"
        f"接受率：{report['valid_acceptance_rate']:.1%}"
    )
    print(
        f"非法编排：{report['invalid_cases']}，"
        f"拒绝率：{report['invalid_rejection_rate']:.1%}"
    )
    print(f"误放行率：{report['false_acceptance_rate']:.1%}")
    print(f"误拒绝率：{report['false_rejection_rate']:.1%}")
    output = ROOT / "data/evaluation/injection_results.json"
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"完整结果已写入 {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
