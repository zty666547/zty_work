"""加载第一版冻结知识库与第二版服务上下文叠加层。"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from src.data.loader import StructuredGraph, load_knowledge_base
from src.graph.schema_v2 import ENTITY_TYPES_V2, RELATION_SIGNATURES_V2


def validate_v2_graph(graph: StructuredGraph) -> list[str]:
    errors: list[str] = []
    types: dict[str, str] = {}
    for entity_type, items in graph.entities.items():
        if entity_type not in ENTITY_TYPES_V2:
            errors.append(f"未知第二版实体类型：{entity_type}")
        for item in items:
            name = item.get("name", "").strip()
            if not name:
                errors.append(f"{entity_type}存在空名称")
            elif name in types:
                errors.append(f"实体名称重复：{name}")
            types[name] = entity_type

    seen = set()
    for relation in graph.relations:
        source = relation.get("source", "")
        target = relation.get("target", "")
        relation_type = relation.get("type", "")
        signature = RELATION_SIGNATURES_V2.get(relation_type)
        if signature is None:
            errors.append(f"未知第二版关系类型：{relation_type}")
        elif source not in types or target not in types:
            errors.append(f"关系端点不存在：{source} -[{relation_type}]-> {target}")
        elif (types[source], types[target]) != signature:
            errors.append(
                f"关系类型不匹配：{source}({types[source]}) -[{relation_type}]-> "
                f"{target}({types[target]})"
            )
        key = (source, relation_type, target)
        if key in seen:
            errors.append(f"关系重复：{source} -[{relation_type}]-> {target}")
        seen.add(key)
    return errors


def load_v2_knowledge_base(
    primary_path: Path,
    evidence_path: Path,
    overlay_path: Path,
) -> StructuredGraph:
    base = load_knowledge_base(primary_path, evidence_path)
    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    graph = deepcopy(base)
    for entity_type, items in overlay.get("entities", {}).items():
        graph.entities.setdefault(entity_type, []).extend(items)
    graph.relations.extend(overlay.get("relations", []))
    graph.source.setdefault("v2_overlays", []).append(overlay.get("source", {}))
    errors = validate_v2_graph(graph)
    if errors:
        raise ValueError("第二版图谱校验失败：\n" + "\n".join(errors[:20]))
    return graph
