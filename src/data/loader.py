"""数据加载：把数据层转成图谱构建/抽取所需的统一结构。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from config.settings import Settings
from src.graph.schema import ENTITY_TYPES, RELATION_SIGNATURES


@dataclass
class StructuredGraph:
    """从结构化 JSON 解析出的图谱数据。"""

    entities: dict[str, list[dict]] = field(default_factory=dict)  # 类型 -> [{name, props}]
    relations: list[dict] = field(default_factory=list)  # [{source, target, type, props}]
    description: str = ""
    source: dict = field(default_factory=dict)

    def entity_names(self) -> set[str]:
        """返回全部实体名，用于去重/校验。"""
        names: set[str] = set()
        for items in self.entities.values():
            for item in items:
                names.add(item["name"])
        return names


def validate_structured(graph: StructuredGraph) -> list[str]:
    """验证实体、关系和端点完整性，返回所有错误。"""
    errors: list[str] = []
    names: set[str] = set()
    entity_type_by_name: dict[str, str] = {}
    if not graph.source.get("title"):
        errors.append("缺少 source.title，无法进行证据溯源")
    for entity_type, items in graph.entities.items():
        if not entity_type.strip():
            errors.append("存在空实体类型")
        elif entity_type not in ENTITY_TYPES:
            errors.append(f"未知实体类型：{entity_type}")
        for index, item in enumerate(items):
            name = str(item.get("name", "")).strip()
            if not name:
                errors.append(f"{entity_type}[{index}] 缺少 name")
            elif name in names:
                errors.append(f"实体名称重复：{name}")
            names.add(name)
            entity_type_by_name[name] = entity_type

    seen_relations: set[tuple[str, str, str]] = set()
    for index, relation in enumerate(graph.relations):
        source = str(relation.get("source", "")).strip()
        target = str(relation.get("target", "")).strip()
        relation_type = str(relation.get("type", "")).strip()
        if source not in names:
            errors.append(f"relations[{index}] 源实体不存在：{source}")
        if target not in names:
            errors.append(f"relations[{index}] 目标实体不存在：{target}")
        if not relation_type:
            errors.append(f"relations[{index}] 缺少 type")
        elif relation_type not in RELATION_SIGNATURES:
            errors.append(f"relations[{index}] 未知关系类型：{relation_type}")
        elif source in entity_type_by_name and target in entity_type_by_name:
            expected_source, expected_target = RELATION_SIGNATURES[relation_type]
            actual = (entity_type_by_name[source], entity_type_by_name[target])
            expected = (expected_source, expected_target)
            if actual != expected:
                errors.append(
                    f"relations[{index}] 方向或类型不符合 Schema："
                    f"{source}({actual[0]}) -[{relation_type}]-> "
                    f"{target}({actual[1]})，应为 {expected[0]} -> {expected[1]}"
                )
        key = (source, target, relation_type)
        if key in seen_relations:
            errors.append(f"关系重复：{source} -[{relation_type}]-> {target}")
        seen_relations.add(key)
    return errors


def load_structured(path: Path) -> StructuredGraph:
    """读取结构化 JSON，并在返回前检查图谱完整性。"""
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    graph = StructuredGraph(
        entities=data["entities"],
        relations=data["relations"],
        description=data.get("description", ""),
        source=data.get("source") or {},
    )
    errors = validate_structured(graph)
    if errors:
        preview = "\n".join(f"- {error}" for error in errors[:20])
        raise ValueError(f"结构化图谱校验失败：\n{preview}")
    return graph


def load_documents(path: Path) -> list[str]:
    """读取原始文本语料，按空行切分为若干条文档（供 LLM 抽取）。"""
    text = path.read_text(encoding="utf-8")
    # 跳过以 # 开头的注释行
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("#")]
    chunks: list[str] = []
    buf: list[str] = []
    for ln in lines:
        if ln.strip():
            buf.append(ln.strip())
        else:
            if buf:
                chunks.append(" ".join(buf))
                buf = []
    if buf:
        chunks.append(" ".join(buf))
    return chunks


def load_input(settings: Settings) -> tuple[StructuredGraph | None, list[str]]:
    """根据抽取模式返回可用的输入。

    返回 (结构化图谱或 None, 文档列表)。
    """
    structured_path = settings.raw_dir / settings.structured_filename
    docs_path = settings.raw_dir / settings.documents_filename

    if settings.extraction_mode == "structured" and structured_path.exists():
        return load_structured(structured_path), []

    return None, load_documents(docs_path)
