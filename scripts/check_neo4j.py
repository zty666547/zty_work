#!/usr/bin/env python3
"""只验证Neo4j连接，不执行查询或修改数据。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings  # noqa: E402
from src.graph.neo4j_client import Neo4jClient  # noqa: E402


def main() -> None:
    client = Neo4jClient(settings)
    try:
        print("Neo4j连接验证通过")
    finally:
        client.close()


if __name__ == "__main__":
    main()
