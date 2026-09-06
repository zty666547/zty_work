"""把已校验知识库转换为确定性的Neo4j待写入产物。"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from src.data.loader import StructuredGraph


def create_graph_artifact(
    graph: StructuredGraph,
    source_files: list[str] | None = None,
) -> dict:
    """展平并稳定排序图谱；相同输入始终生成相同内容指纹。"""
    entities = sorted(
        (
            {
                "name": item["name"],
                "type": entity_type,
                "props": dict(item.get("props") or {}),
            }
            for entity_type, items in graph.entities.items()
            for item in items
        ),
        key=lambda item: (item["type"], item["name"]),
    )
    relations = sorted(
        (
            {
                "source": item["source"],
                "target": item["target"],
                "type": item["type"],
                "props": dict(item.get("props") or {}),
            }
            for item in graph.relations
        ),
        key=lambda item: (item["type"], item["source"], item["target"]),
    )
    core = {"entities": entities, "relations": relations}
    canonical = json.dumps(
        core, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    entity_types = Counter(item["type"] for item in entities)
    relation_types = Counter(item["type"] for item in relations)
    return {
        "format": "debugpath-graph-v1",
        "source_files": sorted(source_files or []),
        "content_sha256": hashlib.sha256(canonical).hexdigest(),
        "stats": {
            "nodes": len(entities),
            "relationships": len(relations),
            "entity_types": dict(sorted(entity_types.items())),
            "relation_types": dict(sorted(relation_types.items())),
        },
        **core,
    }


def write_graph_artifact(artifact: dict, path: Path) -> None:
    """将产物写到固定位置，供审阅、测试与Neo4j构建共用。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
