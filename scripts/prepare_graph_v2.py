#!/usr/bin/env python3
"""校验并生成包含服务上下文的第二版确定性图谱产物。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402
from src.data.loader_v2 import load_v2_knowledge_base  # noqa: E402
from src.graph.artifact import create_graph_artifact, write_graph_artifact  # noqa: E402


def prepare() -> dict:
    primary = settings.raw_dir / settings.structured_filename
    evidence = settings.raw_dir / settings.evidence_filename
    overlay = settings.raw_dir / "debugpath_v2_service_context.json"
    graph = load_v2_knowledge_base(primary, evidence, overlay)
    artifact = create_graph_artifact(
        graph,
        [
            str(primary.relative_to(ROOT)),
            str(evidence.relative_to(ROOT)),
            str(overlay.relative_to(ROOT)),
        ],
    )
    artifact["format"] = "debugpath-graph-v2"
    output = settings.processed_dir / "debugpath_graph_v2.json"
    write_graph_artifact(artifact, output)
    return {"artifact": artifact, "output": output}


def main() -> None:
    result = prepare()
    artifact = result["artifact"]
    print(f"第二版图谱产物：{result['output'].relative_to(ROOT)}")
    print(f"节点：{artifact['stats']['nodes']}")
    print(f"关系：{artifact['stats']['relationships']}")
    print(f"内容指纹：{artifact['content_sha256']}")


if __name__ == "__main__":
    main()
