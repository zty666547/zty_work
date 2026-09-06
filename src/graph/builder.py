"""图谱构建器：把三元组写入 Neo4j，并建立约束与索引。

写入策略：
    - 实体：`MERGE` 到带 `name` 属性的节点，并额外打上实体类型标签（如 :Person）。
    - 关系：`MERGE` 匹配两端的实体节点后创建关系，避免重复。
    - 索引/约束：为 `name` 建立唯一约束，提升检索性能。
"""
from __future__ import annotations

import logging
import re

from config.settings import Settings
from src.graph.neo4j_client import Neo4jClient
from src.graph.schema import RELATION_SIGNATURES
from src.utils.logger import get_logger

logger = get_logger("kg_rag.builder")


_CYPHER_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _quote(identifier: str) -> str:
    """只允许安全的 Cypher 标签、关系类型和属性名。"""
    if not _CYPHER_IDENTIFIER.fullmatch(identifier):
        raise ValueError(f"非法 Cypher 标识符：{identifier!r}")
    return identifier


class GraphBuilder:
    """负责把实体/关系写入 Neo4j 图。"""

    def __init__(self, settings: Settings, client: Neo4jClient):
        self.settings = settings
        self.client = client

    def ensure_constraints(self) -> None:
        """为 Entity.name 建立唯一约束，为实体类型建立索引。"""
        try:
            self.client.run(
                "CREATE CONSTRAINT debugpath_entity_unique IF NOT EXISTS "
                "FOR (n:Entity) REQUIRE (n.project, n.name) IS UNIQUE"
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
            MERGE (n:Entity {{project: 'DebugPath', name: $name}})
            ON CREATE SET n:{label}, n.created_at = datetime()
            ON MATCH SET n:{label}
            """,
            {"name": name},
        )
        # 追加非结构性属性（如出生年份、年份、评分）
        if props:
            safe_keys = [_quote(str(key)) for key in props]
            set_clause = ", ".join(f"n.{key} = $prop_{key}" for key in safe_keys)
            params = {f"prop_{key}": props[key] for key in safe_keys}
            if set_clause:
                self.client.run(
                    f"MATCH (n:Entity {{project: 'DebugPath', name: $name}}) SET {set_clause}",
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
        query = f"""
            MATCH (s:Entity {{project: 'DebugPath', name: $source}})
            MATCH (t:Entity {{project: 'DebugPath', name: $target}})
            MERGE (s)-[r:{rel_type}]->(t)
        """
        params = {"source": source, "target": target}
        if props:
            safe_keys = [_quote(str(key)) for key in props]
            query += " SET " + ", ".join(
                f"r.{key} = $rel_prop_{key}" for key in safe_keys
            )
            params.update({f"rel_prop_{key}": props[key] for key in safe_keys})
        self.client.run(
            query,
            params,
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
        self._validate_input(entities, relations)
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
        expected = {"nodes": len(entities), "relationships": len(relations)}
        if stats != expected:
            raise RuntimeError(
                f"Neo4j写入后规模不一致：期望{expected}，实际{stats}"
            )
        logger.info("图谱构建完成：%s", stats)
        return stats

    def _validate_input(self, entities: list[dict], relations: list[dict]) -> None:
        """在清库前校验输入，避免错误数据破坏已有图谱。"""
        entity_type_by_name: dict[str, str] = {}
        for entity in entities:
            name = str(entity.get("name", "")).strip()
            entity_type = str(entity.get("type", "")).strip()
            if not name or not entity_type:
                raise ValueError(f"实体缺少 name/type：{entity}")
            if entity_type not in self.settings.entity_types:
                raise ValueError(f"实体类型不在 Schema 中：{entity_type}")
            if name in entity_type_by_name:
                raise ValueError(f"实体名称重复：{name}")
            entity_type_by_name[name] = entity_type

        for relation in relations:
            source = relation.get("source")
            target = relation.get("target")
            relation_type = relation.get("type")
            if relation_type not in self.settings.relation_types:
                raise ValueError(f"关系类型不在 Schema 中：{relation_type}")
            if source not in entity_type_by_name or target not in entity_type_by_name:
                raise ValueError(f"关系端点不存在：{source} -> {target}")
            expected = RELATION_SIGNATURES.get(relation_type)
            actual = (entity_type_by_name[source], entity_type_by_name[target])
            if expected and actual != expected:
                raise ValueError(
                    f"关系方向不符合 Schema：{source}({actual[0]}) "
                    f"-[{relation_type}]-> {target}({actual[1]})，"
                    f"应为 {expected[0]} -> {expected[1]}"
                )

    def clear_all(self) -> None:
        """只清理带project=DebugPath标记的项目子图。"""
        self.client.run("MATCH (n:Entity {project: 'DebugPath'}) DETACH DELETE n")
        logger.info("已清空 Neo4j 中的 DebugPath 子图")

    def graph_stats(self) -> dict:
        """返回节点/关系计数用于验证。"""
        node_count = self.client.run(
            "MATCH (n:Entity {project: 'DebugPath'}) RETURN count(n) AS c"
        )[0]["c"]
        rel_count = self.client.run(
            "MATCH (:Entity {project: 'DebugPath'})-[r]->(:Entity {project: 'DebugPath'}) RETURN count(r) AS c"
        )[0]["c"]
        return {"nodes": node_count, "relationships": rel_count}
