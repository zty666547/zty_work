"""基于结构化 JSON 的只读内存图，供离线演示与单元测试使用。"""
from __future__ import annotations

from collections import defaultdict, deque

from src.data.loader import StructuredGraph


class MemoryGraphClient:
    """把 StructuredGraph 转成轻量邻接表，不依赖 Neo4j。"""

    def __init__(self, graph: StructuredGraph):
        self.nodes: dict[str, dict] = {}
        for entity_type, items in graph.entities.items():
            for item in items:
                props = dict(item.get("props") or {})
                props["entity_type"] = entity_type
                self.nodes[item["name"]] = props

        self.relations = [dict(item) for item in graph.relations]
        self.adjacency: dict[str, list[int]] = defaultdict(list)
        for index, relation in enumerate(self.relations):
            self.adjacency[relation["source"]].append(index)
            self.adjacency[relation["target"]].append(index)

    def entity_catalog(self) -> list[dict]:
        return [
            {"name": name, "aliases": props.get("aliases", [])}
            for name, props in self.nodes.items()
        ]

    def expand_neighborhood(self, entity_name: str, hop: int = 2) -> list[dict]:
        if entity_name not in self.nodes or hop < 1:
            return []

        queue = deque([(entity_name, 0)])
        visited_nodes = {entity_name}
        visited_edges: set[int] = set()
        triples: list[dict] = []

        while queue:
            current, depth = queue.popleft()
            if depth >= hop:
                continue
            for edge_index in self.adjacency[current]:
                relation = self.relations[edge_index]
                if edge_index not in visited_edges:
                    visited_edges.add(edge_index)
                    triples.append(
                        {
                            "source": relation["source"],
                            "source_props": self.nodes[relation["source"]],
                            "rel": relation["type"],
                            "rel_props": relation.get("props") or {},
                            "target": relation["target"],
                            "target_props": self.nodes[relation["target"]],
                        }
                    )
                neighbor = (
                    relation["target"]
                    if relation["source"] == current
                    else relation["source"]
                )
                if neighbor not in visited_nodes:
                    visited_nodes.add(neighbor)
                    queue.append((neighbor, depth + 1))
        return triples
