"""图检索器：从知识图谱中召回与问题相关的子图。

流程（经典 Graph RAG 检索路径）：
    1) 实体链接：把问题中的实体指称匹配到图谱中的节点
    2) 邻域扩展：沿关系向外扩展 N 跳，得到相关子图
    3) 上下文组装：把子图三元组拼成文本，交给生成模型

这里实体链接采用“字符串包含匹配 + 小写归一化”的离线方案，无需额外调用大模型，
保证问答链路稳定可控；也可扩展为 LLM 实体抽取。
"""
from __future__ import annotations

import logging

from src.graph.neo4j_client import Neo4jClient
from src.rag.prompts import build_context_text
from src.utils.logger import get_logger

logger = get_logger("kg_rag.retriever")


class GraphRetriever:
    """基于 Cypher 的图检索器。"""

    def __init__(self, client: Neo4jClient):
        self.client = client

    def all_entity_names(self) -> list[str]:
        """获取图谱全部实体名，用于实体链接。"""
        rows = self.client.run("MATCH (n:Entity) RETURN n.name AS name")
        return [r["name"] for r in rows]

    def link_entities(self, question: str, max_entities: int = 5) -> list[str]:
        """把问题中指称的实体匹配到图谱已有实体，返回命中的实体名。"""
        q_lower = question.lower()
        matched: list[str] = []
        for name in self.all_entity_names():
            name_lower = name.lower()
            # 实体名是问题的子串，或问题包含实体名
            if name_lower and (name_lower in q_lower or q_lower in name_lower):
                matched.append(name)
        # 简单按名称长度排序，优先保留更具体的实体
        matched.sort(key=len, reverse=True)
        return matched[:max_entities]

    def expand_neighborhood(self, entity_name: str, hop: int = 2) -> list[dict]:
        """从给定实体向外扩展 hop 跳，返回三元组形式的子图。

        使用 Neo4j 可变长路径查询获取 (源, 关系, 目标) 三元组。
        """
        query = f"""
        MATCH path = (start:Entity {{name: $name}})-[*1..{hop}]-(neighbor:Entity)
        UNWIND relationships(path) AS r
        RETURN collect(DISTINCT {{
            source: startNode(r).name,
            rel: type(r),
            target: endNode(r).name
        }}) AS triples
        """
        rows = self.client.run(query, {"name": entity_name})
        if not rows or not rows[0].get("triples"):
            return []
        # collect 可能返回嵌套数组，做扁平化与去重
        seen: set[tuple] = set()
        result: list[dict] = []
        raw = rows[0]["triples"]
        if raw and isinstance(raw[0], dict):
            items = raw
        else:
            items = []
            for nest in raw:
                if isinstance(nest, list):
                    items.extend(nest)
        for t in items:
            key = (t["source"], t["rel"], t["target"])
            if key not in seen:
                seen.add(key)
                result.append({"source": t["source"], "rel": t["rel"], "target": t["target"]})
        return result

    def retrieve(self, question: str, hop: int = 2) -> dict:
        """检索入口：返回 {entities, context_text, triples}。"""
        entities = self.link_entities(question)
        logger.info("问题「%s」链接到实体：%s", question, entities)

        triples: list[dict] = []
        for ent in entities:
            triples.extend(self.expand_neighborhood(ent, hop=hop))

        # 三元组去重
        seen: set[tuple] = set()
        unique: list[dict] = []
        for t in triples:
            key = (t["source"], t["rel"], t["target"])
            if key not in seen:
                seen.add(key)
                unique.append(t)

        context_text = build_context_text(unique)
        return {"entities": entities, "triples": unique, "context_text": context_text}
