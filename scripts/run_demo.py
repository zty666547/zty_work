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

# 建议在答辩时演示的问题（覆盖图谱多跳查询）
# 注意：示例数据实体为英文名，问题中请包含英文实体以便链接
DEMO_QUESTIONS = [
    "克里斯托弗·诺兰（Christopher Nolan）导演了哪些电影？",
    "莱昂纳多·迪卡普里奥（Leonardo DiCaprio）参演过哪些电影？",
    "肖申克的救赎（The Shawshank Redemption）是什么类型的电影？",
    "The Dark Knight 的导演还导演过哪些电影？",
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
