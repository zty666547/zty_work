"""数据加载：把数据层转成图谱构建/抽取所需的统一结构。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from config.settings import Settings


@dataclass
class StructuredGraph:
    """从结构化 JSON 解析出的图谱数据。"""

    entities: dict[str, list[dict]] = field(default_factory=dict)  # 类型 -> [{name, props}]
    relations: list[dict] = field(default_factory=list)  # [{source, target, type, props}]

    def entity_names(self) -> set[str]:
        """返回全部实体名，用于去重/校验。"""
        names: set[str] = set()
        for items in self.entities.values():
            for item in items:
                names.add(item["name"])
        return names


def load_structured(path: Path) -> StructuredGraph:
    """读取 `movies_structured.json` 得到图谱三元组。"""
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return StructuredGraph(entities=data["entities"], relations=data["relations"])


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
    structured_path = settings.raw_dir / "movies_structured.json"
    docs_path = settings.raw_dir / "movie_docs.txt"

    if settings.extraction_mode == "structured" and structured_path.exists():
        return load_structured(structured_path), []

    return None, load_documents(docs_path)
