#!/usr/bin/env python3
"""校验、合并并生成确定性的Neo4j待写入图谱。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402
from src.data.loader import load_knowledge_base  # noqa: E402
from src.graph.artifact import create_graph_artifact, write_graph_artifact  # noqa: E402


def prepare() -> dict:
    primary = settings.raw_dir / settings.structured_filename
    evidence = settings.raw_dir / settings.evidence_filename
    graph = load_knowledge_base(primary, evidence)
    artifact = create_graph_artifact(
        graph,
        [str(primary.relative_to(ROOT)), str(evidence.relative_to(ROOT))],
    )
    output = settings.processed_dir / "debugpath_graph.json"
    write_graph_artifact(artifact, output)
    return {"artifact": artifact, "output": output}


def main() -> None:
    result = prepare()
    artifact = result["artifact"]
    print(f"图谱产物：{result['output'].relative_to(ROOT)}")
    print(f"节点：{artifact['stats']['nodes']}")
    print(f"关系：{artifact['stats']['relationships']}")
    print(f"内容指纹：{artifact['content_sha256']}")


if __name__ == "__main__":
    main()
