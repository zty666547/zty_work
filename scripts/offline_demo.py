#!/usr/bin/env python3
"""无需 Neo4j 和 API Key 的图检索演示。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings  # noqa: E402
from src.data.loader import load_knowledge_base  # noqa: E402
from src.graph.memory_client import MemoryGraphClient  # noqa: E402
from src.rag.retriever import GraphRetriever  # noqa: E402


DEMO_QUESTIONS = [
    "知识工程是多少学分，建议在哪个学期修读？",
    "选修课和通识课是什么关系？",
    "专业核心与专业选修有什么区别？",
    "建议修读学期是否具有强制性？",
    "四史类课程是每一门都必修吗？",
]


def main() -> None:
    path = settings.raw_dir / settings.structured_filename
    client = MemoryGraphClient(
        load_knowledge_base(path, settings.raw_dir / settings.rules_filename)
    )
    retriever = GraphRetriever(client)
    questions = sys.argv[1:] or DEMO_QUESTIONS

    for question in questions:
        result = retriever.retrieve(question, hop=1)
        print(f"\n【问题】{question}")
        print(f"【命中实体】{', '.join(result['entities']) or '无'}")
        print(f"【识别意图】{', '.join(result['intents']) or '通用查询'}")
        print(f"【关系过滤】{', '.join(result['relation_filter']) or '无'}")
        print("【检索证据】")
        print(result["context_text"])


if __name__ == "__main__":
    main()
