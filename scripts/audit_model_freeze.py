#!/usr/bin/env python3
"""确认当前图谱和诊断设置仍与第二阶段冻结版本一致。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import Settings  # noqa: E402

FREEZE_PATH = ROOT / "data/evaluation/model_freeze.json"
GRAPH_PATH = ROOT / "data/processed/debugpath_graph.json"


def build_report() -> dict:
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    settings = Settings()
    mismatches = []
    if graph["content_sha256"] != freeze["graph_content_sha256"]:
        mismatches.append("graph_content_sha256")
    for name, expected in freeze["settings"].items():
        actual = getattr(settings, name)
        if actual != expected:
            mismatches.append(f"settings.{name}: expected={expected}, actual={actual}")
    return {
        "freeze_id": freeze["freeze_id"],
        "graph_matches": graph["content_sha256"] == freeze["graph_content_sha256"],
        "settings_checked": len(freeze["settings"]),
        "mismatches": mismatches,
        "frozen": not mismatches,
        "test_protocol": freeze["test_protocol"],
    }


def main() -> None:
    report = build_report()
    print(f"冻结版本：{report['freeze_id']}")
    print(f"图谱指纹：{'一致' if report['graph_matches'] else '已变化'}")
    print(f"已核对设置：{report['settings_checked']}项")
    if report["mismatches"]:
        raise SystemExit("冻结审计失败：" + "；".join(report["mismatches"]))
    print("冻结审计通过，可以继续收集未见测试案例。")


if __name__ == "__main__":
    main()
