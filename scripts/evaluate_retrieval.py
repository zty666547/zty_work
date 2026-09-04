#!/usr/bin/env python3
"""离线计算实体链接与证据召回准确率。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402
from src.data.loader import load_knowledge_base  # noqa: E402
from src.graph.memory_client import MemoryGraphClient  # noqa: E402
from src.rag.retriever import GraphRetriever  # noqa: E402


def evaluate(cases: list[dict], retriever: GraphRetriever, strategy: str) -> dict:
    """评测一种检索策略，返回可用于对比的指标。"""
    entity_hits = 0
    context_hits = 0

    for case in cases:
        result = retriever.retrieve(case["question"], hop=1, strategy=strategy)
        entity_ok = all(item in result["entities"] for item in case["expected_entities"])
        expected_ok = all(
            item in result["context_text"] for item in case["expected_context"]
        )
        forbidden_ok = all(
            item not in result["context_text"]
            for item in case.get("forbidden_context", [])
        )
        context_ok = expected_ok and forbidden_ok
        entity_hits += entity_ok
        context_hits += context_ok
        print(
            f"[{'PASS' if entity_ok and context_ok else 'FAIL'}] "
            f"{case['question']}"
        )

    total = len(cases)
    return {
        "entity_hits": entity_hits,
        "context_hits": context_hits,
        "total": total,
    }


def main() -> None:
    cases = json.loads((ROOT / "data/evaluation/questions.json").read_text())
    graph = load_knowledge_base(
        settings.raw_dir / settings.structured_filename,
        settings.raw_dir / settings.rules_filename,
    )
    retriever = GraphRetriever(MemoryGraphClient(graph))
    results = {}

    for strategy in ("baseline", "enhanced"):
        print(f"\n=== {strategy} ===")
        results[strategy] = evaluate(cases, retriever, strategy)
        result = results[strategy]
        total = result["total"]
        print(
            f"实体链接准确率：{result['entity_hits']}/{total} "
            f"= {result['entity_hits'] / total:.0%}"
        )
        print(
            f"证据检索成功率：{result['context_hits']}/{total} "
            f"= {result['context_hits'] / total:.0%}"
        )

    enhanced = results["enhanced"]
    if enhanced["entity_hits"] != enhanced["total"] or enhanced["context_hits"] != enhanced["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
