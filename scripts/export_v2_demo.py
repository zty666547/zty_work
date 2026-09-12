#!/usr/bin/env python3
"""导出可重复的第二版完整诊断轨迹与逐步子图。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.diagnosis.service_v2 import DiagnosisServiceV2  # noqa: E402
from src.diagnosis.trajectory_v2 import stage_subgraph  # noqa: E402

SCENARIO_PATH = ROOT / "data/demo/open_webui_ollama.json"
OUTPUT_PATH = ROOT / "data/demo/open_webui_ollama_trajectory.json"


def build_demo() -> dict:
    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    service = DiagnosisServiceV2()
    snapshot = service.start(scenario["report"])
    while snapshot["state"]["status"] == "questioning":
        question = snapshot["question"]
        if not question:
            break
        answer = scenario["answers"].get(question["name"], "unknown")
        snapshot = service.answer(snapshot["state"], question["name"], answer)

    trajectory = snapshot["state"]["trajectory"]
    subgraphs = [
        stage_subgraph(
            stage,
            service.graph,
            trajectory[index - 1] if index else None,
        )
        for index, stage in enumerate(trajectory)
    ]
    final = snapshot["candidates"][0]
    return {
        "format": "debugpath-demo-v2",
        "scenario": scenario,
        "graph": {
            "nodes": sum(len(items) for items in service.graph.entities.values()),
            "relations": len(service.graph.relations),
        },
        "routing": snapshot["routing"],
        "service_context": snapshot["service_context"],
        "trajectory": trajectory,
        "subgraphs": subgraphs,
        "final": {
            "cause": final["name"],
            "probability": final["probability"],
            "decision": snapshot["decision"],
            "stop_reason": snapshot["state"]["stop_reason"],
            "plan": snapshot["plan"][0],
            "plan_errors": snapshot["plan_errors"],
        },
    }


def main() -> None:
    report = build_demo()
    OUTPUT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"演示轨迹：{len(report['trajectory'])}个阶段；"
        f"最终原因={report['final']['cause']}；"
        f"概率={report['final']['probability']:.1%}"
    )
    print(f"已写入：{OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
