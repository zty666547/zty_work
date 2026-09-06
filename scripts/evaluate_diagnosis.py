#!/usr/bin/env python3
"""离线评估主动追问后能否把预期原因排到首位。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.diagnosis.service import DiagnosisService  # noqa: E402


def run_case(service: DiagnosisService, case: dict) -> dict:
    snapshot = service.start(case["report"])
    while snapshot["question"] and snapshot["state"]["status"] == "questioning":
        question = snapshot["question"]["name"]
        answer = case["answers"].get(question, "unknown")
        snapshot = service.answer(snapshot["state"], question, answer)
    predicted = snapshot["candidates"][0]
    return {
        "id": case["id"],
        "expected": case["expected_top_cause"],
        "predicted": predicted["name"],
        "probability": predicted["probability"],
        "questions": len(snapshot["state"]["asked_questions"]),
        "passed": predicted["name"] == case["expected_top_cause"],
    }


def main() -> None:
    cases = json.loads((ROOT / "data/evaluation/diagnosis_cases.json").read_text(encoding="utf-8"))
    service = DiagnosisService()
    results = [run_case(service, case) for case in cases]
    for item in results:
        mark = "PASS" if item["passed"] else "FAIL"
        print(f"{mark} {item['id']}: {item['predicted']} ({item['probability']:.1%}), 追问{item['questions']}次")
    passed = sum(item["passed"] for item in results)
    print(f"\nTop-1原因命中：{passed}/{len(results)} = {passed / len(results):.1%}")
    raise SystemExit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
