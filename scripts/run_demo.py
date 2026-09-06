#!/usr/bin/env python3
"""答辩用离线演示：展示三个领域的首次主动问题。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.diagnosis.service import DiagnosisService  # noqa: E402


def main() -> None:
    service = DiagnosisService()
    reports = [
        "ModuleNotFoundError: No module named pandas",
        "torch.cuda.is_available() False，检测不到GPU",
        "Neo4j Connection refused",
    ]
    for report in reports:
        snapshot = service.start(report)
        top = snapshot["candidates"][0]
        print(f"\n故障：{report}")
        print(f"识别：{snapshot['state']['issue_name']}")
        print(f"初始首因：{top['name']} {top['probability']:.1%}")
        print(f"主动追问：{snapshot['question']['text']}")
        print(f"选择理由：{snapshot['question']['reason']}")


if __name__ == "__main__":
    main()
