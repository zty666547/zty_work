#!/usr/bin/env python3
"""无需Neo4j和API密钥的主动诊断演示。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.diagnosis.generator import render_offline  # noqa: E402
from src.diagnosis.service import DiagnosisService  # noqa: E402


def main() -> None:
    service = DiagnosisService()
    snapshot = service.start("ModuleNotFoundError: No module named 'pandas'")
    print("场景：", snapshot["state"]["issue_name"])
    while snapshot["question"] and len(snapshot["state"]["asked_questions"]) < 2:
        question = snapshot["question"]
        answer = "no" if question["name"] == "Q-包是否可见" else "yes"
        print(f"追问：{question['text']} -> {answer}")
        snapshot = service.answer(snapshot["state"], question["name"], answer)
    snapshot = service.complete(snapshot["state"])
    print(render_offline(snapshot))


if __name__ == "__main__":
    main()
