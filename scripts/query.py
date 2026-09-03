#!/usr/bin/env python3
"""交互式问答 CLI。

用法：
    python scripts/query.py "诺兰导演了哪些电影？"
    echo "诺兰导演了哪些电影？" | python scripts/query.py
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

logger = get_logger("kg_rag.query")


def ask(chain: GraphRAGChain, question: str) -> None:
    result = chain.answer(question, show_context=True)
    print(f"\n【问题】{result['question']}")
    print(f"【答案】{result['answer']}")
    print(f"【命中的实体】{result['entities']}")


def main() -> None:
    questions = sys.argv[1:] or [ln.strip() for ln in sys.stdin if ln.strip()]
    if not questions:
        print("用法：python scripts/query.py \"你的问题\"")
        return

    client = Neo4jClient(settings)
    try:
        llm = LLMClient(settings)
        chain = GraphRAGChain(settings, client, llm)
        for q in questions:
            ask(chain, q)
    finally:
        client.close()


if __name__ == "__main__":
    main()
