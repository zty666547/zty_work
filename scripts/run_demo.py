#!/usr/bin/env python3
"""一键演示：构建图谱 + 示例问答，适合期末答辩/汇报。

用法：
    python scripts/run_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings  # noqa: E402
from src.extraction.llm_client import LLMClient  # noqa: E402
from src.graph.neo4j_client import Neo4jClient  # noqa: E402
from src.rag.chain import GraphRAGChain  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402

logger = get_logger("kg_rag.demo")

# 建议在答辩时演示的问题（覆盖属性、关系和组合条件查询）
DEMO_QUESTIONS = [
    "知识工程是多少学分，建议在哪个学期修读？",
    "第四学期有哪些专业核心课？",
    "NLP 属于什么类型的课程？",
    "第六学期有哪些专业选修课？",
]


def main() -> None:
    # 1) 先用构建脚本建图（复用其逻辑）
    import importlib.util

    script = Path(__file__).resolve().parent / "build_kg.py"
    spec = importlib.util.spec_from_file_location("build_kg", script)
    build_kg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_kg)
    build_kg.main()

    # 2) 交互问答
    client = Neo4jClient(settings)
    try:
        llm = LLMClient(settings)
        chain = GraphRAGChain(settings, client, llm)
        for q in DEMO_QUESTIONS:
            result = chain.answer(q, show_context=True)
            print(f"\n【问题】{result['question']}")
            print(f"【答案】{result['answer']}")
            print(f"【命中的实体】{result['entities']}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
