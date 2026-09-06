#!/usr/bin/env python3
"""命令行主动诊断。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.diagnosis.generator import render_offline  # noqa: E402
from src.diagnosis.service import DiagnosisService  # noqa: E402


def main() -> None:
    report = " ".join(sys.argv[1:]).strip()
    if not report:
        print('用法：python scripts/query.py "ModuleNotFoundError: No module named pandas"')
        return
    service = DiagnosisService()
    snapshot = service.start(report)
    print(f"识别场景：{snapshot['state']['issue_name']}")
    while snapshot["question"] and snapshot["state"]["status"] == "questioning":
        question = snapshot["question"]
        print(f"\n{question['text']}")
        print(question["reason"])
        raw = input(f"[y] {question['yes_label']} / [n] {question['no_label']} / [u] 不确定 / [q] 结束：").strip().lower()
        if raw == "q":
            snapshot = service.complete(snapshot["state"])
            break
        answer = {"y": "yes", "n": "no", "u": "unknown"}.get(raw, "unknown")
        snapshot = service.answer(snapshot["state"], question["name"], answer)
    print("\n" + render_offline(snapshot))


if __name__ == "__main__":
    main()
