#!/usr/bin/env python3
"""离线计算实体链接与证据召回准确率。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import settings  # noqa: E402
from src.data.loader import load_structured  # noqa: E402
from src.graph.memory_client import MemoryGraphClient  # noqa: E402
from src.rag.retriever import GraphRetriever  # noqa: E402


def main() -> None:
    cases = json.loads((ROOT / "data/evaluation/questions.json").read_text())
    graph = load_structured(settings.raw_dir / settings.structured_filename)
    retriever = GraphRetriever(MemoryGraphClient(graph))
    entity_hits = 0
    context_hits = 0

    for case in cases:
        result = retriever.retrieve(case["question"], hop=1)
        entity_ok = all(item in result["entities"] for item in case["expected_entities"])
        context_ok = all(item in result["context_text"] for item in case["expected_context"])
        entity_hits += entity_ok
        context_hits += context_ok
        print(f"[{'PASS' if entity_ok and context_ok else 'FAIL'}] {case['question']}")

    total = len(cases)
    print(f"\n实体链接准确率：{entity_hits}/{total} = {entity_hits / total:.0%}")
    print(f"证据召回成功率：{context_hits}/{total} = {context_hits / total:.0%}")
    if entity_hits != total or context_hits != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

