#!/usr/bin/env python3
"""只读核验Neo4j中的DebugPath子图是否与本地产物一致。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings  # noqa: E402
from src.data.loader import load_knowledge_base  # noqa: E402
from src.graph.artifact import create_graph_artifact  # noqa: E402
from src.graph.neo4j_client import Neo4jClient  # noqa: E402


def inspect_remote(client: Neo4jClient) -> dict:
    nodes = client.run(
        "MATCH (n:Entity {project: 'DebugPath'}) RETURN count(n) AS count"
    )[0]["count"]
    relationships = client.run(
        "MATCH (:Entity {project: 'DebugPath'})-[r]->"
        "(:Entity {project: 'DebugPath'}) RETURN count(r) AS count"
    )[0]["count"]
    entity_types = client.run(
        "MATCH (n:Entity {project: 'DebugPath'}) "
        "UNWIND [label IN labels(n) WHERE label <> 'Entity'] AS entity_type "
        "RETURN entity_type, count(*) AS count ORDER BY entity_type"
    )
    relation_types = client.run(
        "MATCH (:Entity {project: 'DebugPath'})-[r]->"
        "(:Entity {project: 'DebugPath'}) "
        "RETURN type(r) AS relation_type, count(*) AS count ORDER BY relation_type"
    )
    return {
        "nodes": nodes,
        "relationships": relationships,
        "entity_types": {item["entity_type"]: item["count"] for item in entity_types},
        "relation_types": {
            item["relation_type"]: item["count"] for item in relation_types
        },
    }


def main() -> None:
    primary = settings.raw_dir / settings.structured_filename
    evidence = settings.raw_dir / settings.evidence_filename
    expected = create_graph_artifact(
        load_knowledge_base(primary, evidence)
    )["stats"]
    client = Neo4jClient(settings)
    try:
        actual = inspect_remote(client)
    finally:
        client.close()
    if actual != expected:
        raise RuntimeError(f"Neo4j图谱与本地知识库不一致：期望{expected}，实际{actual}")
    print("Neo4j连接与图谱一致性验证通过")
    print(f"节点：{actual['nodes']}，关系：{actual['relationships']}")


if __name__ == "__main__":
    main()
