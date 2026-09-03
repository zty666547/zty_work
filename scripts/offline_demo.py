#!/usr/bin/env python3
"""无需 Neo4j 和 API Key 的图检索演示。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings  # noqa: E402
from src.data.loader import load_structured  # noqa: E402
from src.graph.memory_client import MemoryGraphClient  # noqa: E402
from src.rag.retriever import GraphRetriever  # noqa: E402


DEMO_QUESTIONS = [
    "知识工程是多少学分，建议在哪个学期修读？",
    "第四学期有哪些专业核心课？",
    "NLP属于什么类型的课程？",
    "第六学期有哪些专业选修课？",
]


def main() -> None:
    path = settings.raw_dir / settings.structured_filename
    client = MemoryGraphClient(load_structured(path))
    retriever = GraphRetriever(client)
    questions = sys.argv[1:] or DEMO_QUESTIONS

    for question in questions:
        result = retriever.retrieve(question, hop=1)
        print(f"\n【问题】{question}")
        print(f"【命中实体】{', '.join(result['entities']) or '无'}")
        print("【检索证据】")
        print(result["context_text"])


if __name__ == "__main__":
    main()
