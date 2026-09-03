#!/usr/bin/env python3
"""构建知识图谱。

用法（在项目根目录执行）：
    python scripts/build_kg.py

会根据 `.env` 的 EXTRACTION_MODE 选择：
    structured -> 从 data/raw/movies_structured.json 直接建图（无需 LLM）
    llm        -> 用 DeepSeek 从 data/raw/movie_docs.txt 抽取实体关系后再建图
"""
from __future__ import annotations

import sys
from pathlib import Path

# 保证能以 scripts 为起点导入 src/ 与 config/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings  # noqa: E402
from src.data.loader import load_input  # noqa: E402
from src.extraction.llm_client import LLMClient  # noqa: E402
from src.extraction.extractor import EntityRelationExtractor  # noqa: E402
from src.graph.builder import GraphBuilder  # noqa: E402
from src.graph.neo4j_client import Neo4jClient  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402

logger = get_logger("kg_rag.build_kg")


def main() -> None:
    logger.info("构建开始，抽取模式 = %s", settings.extraction_mode)

    structured, documents = load_input(settings)

    entities: list[dict] = []
    relations: list[dict] = []

    if structured is not None:
        # 结构化模式：把按类型分组的实体展平，带 props
        for etype, items in structured.entities.items():
            for item in items:
                entities.append({"name": item["name"], "type": etype, "props": item.get("props", {})})
        relations = list(structured.relations)
        logger.info("已加载结构化三元组：%d 实体，%d 关系", len(entities), len(relations))
    else:
        # LLM 抽取模式
        llm = LLMClient(settings)
        extractor = EntityRelationExtractor(settings, llm)
        merged = extractor.extract_batch(documents)
        entities = [
            {"name": e["name"], "type": e["type"], "props": {}}
            for e in merged["entities"]
        ]
        relations = list(merged["relations"])
        logger.info(
            "LLM 抽取完成：%d 实体，%d 关系", len(entities), len(relations)
        )

    if not entities:
        logger.warning("没有可写入的三元组，请检查数据与抽取模式。")
        return

    client = Neo4jClient(settings)
    try:
        builder = GraphBuilder(settings, client)
        stats = builder.build(entities, relations, clear_first=True)
        logger.info("构建完成，图谱规模：%s", stats)
    finally:
        client.close()


if __name__ == "__main__":
    main()
