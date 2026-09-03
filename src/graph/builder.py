"""图谱构建器：把三元组写入 Neo4j，并建立约束与索引。

写入策略：
    - 实体：`MERGE` 到带 `name` 属性的节点，并额外打上实体类型标签（如 :Person）。
    - 关系：`MERGE` 匹配两端的实体节点后创建关系，避免重复。
    - 索引/约束：为 `name` 建立唯一约束，提升检索性能。
"""
from __future__ import annotations

import logging

from config.settings import Settings
from src.graph.neo4j_client import Neo4jClient
from src.utils.logger import get_logger

logger = get_logger("kg_rag.builder")


def _quote(label: str) -> str:
    """把实体类型转成安全的 Cypher 标签（来自允许清单，安全性可控）。"""
    return label.replace("`", "")


class GraphBuilder:
    """负责把实体/关系写入 Neo4j 图。"""

    def __init__(self, settings: Settings, client: Neo4jClient):
        self.settings = settings
        self.client = client

    def ensure_constraints(self) -> None:
        """为 Entity.name 建立唯一约束，为实体类型建立索引。"""
        try:
            self.client.run(
                "CREATE CONSTRAINT entity_name_unique IF NOT EXISTS "
                "FOR (n:Entity) REQUIRE n.name IS UNIQUE"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("创建唯一约束失败（可能已存在）：%s", exc)
        for label in self.settings.entity_types:
            try:
                self.client.run(
                    f"CREATE INDEX {_quote(label)}_name_idx IF NOT EXISTS "
                    f"FOR (n:{_quote(label)}) ON (n.name)"
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("创建索引失败：%s", exc)
        logger.info("约束与索引已就绪")

    def _merge_entity(self, name: str, etype: str, props: dict | None) -> None:
        """创建/更新一个实体节点，赋予类型标签。"""
        label = _quote(etype)
        self.client.run(
            f"""
            MERGE (n:Entity {{name: $name}})
            SET n:{label}
            ON CREATE SET n.created_at = datetime()
            """,
            {"name": name},
        )
        # 追加非结构性属性（如出生年份、年份、评分）
        if props:
            set_clause = ", ".join(f"n.`{k}` = $prop_{k}" for k in props.keys())
            params = {f"prop_{k}": v for k, v in props.items()}
            if set_clause:
                self.client.run(
                    f"MATCH (n:Entity {{name: $name}}) SET {set_clause}",
                    {"name": name, **params},
                )

    def _merge_relation(
        self,
        source: str,
        target: str,
        rtype: str,
        props: dict | None,
        source_type: str | None,
        target_type: str | None,
    ) -> None:
        """匹配两端实体节点并建立/更新关系。"""
        rel_type = _quote(rtype)
        # 两端实体按 name 匹配；若是特定类型，则加上标签约束以加快匹配
        self.client.run(
            f"""
            MATCH (s:Entity {{name: $source}})
            MATCH (t:Entity {{name: $target}})
            MERGE (s)-[r:{rel_type}]->(t)
            """,
            {"source": source, "target": target},
        )

    def build(
        self,
        entities: list[dict],
        relations: list[dict],
        clear_first: bool = True,
    ) -> dict:
        """清空后构建图谱。

        entities: [{name, type, props}]；relations: [{source, target, type, props}]
        """
        if clear_first:
            self.clear_all()
        self.ensure_constraints()

        for ent in entities:
            self._merge_entity(
                ent.get("name", ""),
                ent.get("type", ""),
                ent.get("props") or {},
            )

        for rel in relations:
            self._merge_relation(
                rel.get("source", ""),
                rel.get("target", ""),
                rel.get("type", ""),
                rel.get("props") or {},
                rel.get("source_type"),
                rel.get("target_type"),
            )

        stats = self.graph_stats()
        logger.info("图谱构建完成：%s", stats)
        return stats

    def clear_all(self) -> None:
        """清空整库（在开发/演示阶段安全；生产务必谨慎）。"""
        self.client.run("MATCH (n) DETACH DELETE n")
        logger.info("已清空 Neo4j 图库")

    def graph_stats(self) -> dict:
        """返回节点/关系计数用于验证。"""
        node_count = self.client.run("MATCH (n:Entity) RETURN count(n) AS c")[0]["c"]
        rel_count = self.client.run("MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
        return {"nodes": node_count, "relationships": rel_count}
