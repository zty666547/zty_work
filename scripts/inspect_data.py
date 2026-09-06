#!/usr/bin/env python3
"""离线检查DebugPath图谱规模与Schema。"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings  # noqa: E402
from src.data.loader import load_knowledge_base  # noqa: E402


def main() -> None:
    path = settings.raw_dir / settings.structured_filename
    evidence_path = settings.raw_dir / settings.evidence_filename
    graph = load_knowledge_base(path, evidence_path)
    entity_counts = {name: len(items) for name, items in graph.entities.items()}
    relation_counts = Counter(item["type"] for item in graph.relations)
    print(f"资料来源：{graph.source.get('title', '未标注')}")
    print(f"核验日期：{graph.source.get('verified_on', '未标注')}")
    print(f"实体总数：{sum(entity_counts.values())}")
    for name, count in sorted(entity_counts.items()):
        print(f"  - {name}: {count}")
    print(f"关系总数：{len(graph.relations)}")
    for name, count in sorted(relation_counts.items()):
        print(f"  - {name}: {count}")
    print("Schema与端点校验：通过")


if __name__ == "__main__":
    main()
