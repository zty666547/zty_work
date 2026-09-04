#!/usr/bin/env python3
"""离线检查培养方案图谱数据，不连接 Neo4j、不调用大模型。"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings  # noqa: E402
from src.data.loader import load_knowledge_base  # noqa: E402


def main() -> None:
    path = settings.raw_dir / settings.structured_filename
    graph = load_knowledge_base(path, settings.raw_dir / settings.rules_filename)
    print(f"资料来源：{graph.source.get('title', '未标注')}")
    source_date = graph.source.get("revision_date") or graph.source.get(
        "official_page_date", "未标注"
    )
    print(f"来源日期：{source_date}")
    entity_counts = {name: len(items) for name, items in graph.entities.items()}
    relation_counts = Counter(item["type"] for item in graph.relations)

    print(f"数据文件：{path.name}")
    print(f"实体总数：{sum(entity_counts.values())}")
    for name, count in sorted(entity_counts.items()):
        print(f"  - {name}: {count}")
    print(f"关系总数：{len(graph.relations)}")
    for name, count in sorted(relation_counts.items()):
        print(f"  - {name}: {count}")
    print("校验结果：通过")


if __name__ == "__main__":
    main()
