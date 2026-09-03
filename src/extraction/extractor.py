"""基于大模型的信息抽取（LLM-based Information Extraction）。

输入：一条自然语言文档
输出：从文本中识别出的实体（含类型）与三元组关系。

核心思路：用一段约束 Prompt + 固定 JSON Schema 引导模型，把非结构化文本
转为 (实体, 关系, 实体) 三元组，从而构建知识图谱。
"""
from __future__ import annotations

import logging

from config.settings import Settings
from src.extraction.llm_client import LLMClient
from src.utils.logger import get_logger

logger = get_logger("kg_rag.extractor")

SYSTEM_PROMPT = """你是一名知识图谱构建专家，擅长从自然语言文本中抽取实体与关系。
只输出 JSON，不要输出任何解释性文字。"""


def _build_user_prompt(text: str, entity_types: list[str], relation_types: list[str]) -> str:
    types_str = ", ".join(entity_types)
    rels_str = ", ".join(relation_types)
    return f"""请从下面的文本中抽取知识三元组。

可抽取的实体类型（Entity Type）：{types_str}
可抽取的关系类型（Relation Type）：{rels_str}

要求：
1. 实体名使用文本中的原语言名称。
2. 关系方向必须符合语义（如 导演 -> 电影，用 DIRECTED）。
3. 同一实体在不同文档中出现时保持名称一致。

请严格按以下 JSON 格式输出，不要多余内容：
{{
  "entities": [
    {{"name": "实体名", "type": "实体类型 | 只能是 {types_str} 之一"}}
  ],
  "relations": [
    {{"source": "源实体名", "target": "目标实体名", "type": "关系类型 | 只能是 {rels_str} 之一"}}
  ]
}}

待抽取文本：
---
{text}
---"""


class EntityRelationExtractor:
    """用大模型从文档中抽取实体与关系。"""

    def __init__(self, settings: Settings, llm: LLMClient):
        self.settings = settings
        self.llm = llm

    def extract(self, document: str) -> dict:
        """抽取单条文档，返回 {entities, relations}。"""
        prompt = _build_user_prompt(
            document, self.settings.entity_types, self.settings.relation_types
        )
        result = self.llm.chat_json(SYSTEM_PROMPT, prompt)
        entities = result.get("entities", [])
        relations = result.get("relations", [])
        logger.info("抽取到 %d 个实体、%d 条关系", len(entities), len(relations))
        return {"entities": entities, "relations": relations}

    def extract_batch(self, documents: list[str]) -> dict:
        """批量抽取并合并去重。

        合并策略：实体按 (name, type) 去重；关系按 (source, target, type) 去重。
        """
        merged_entities: dict[tuple, dict] = {}
        merged_relations: dict[tuple, dict] = {}

        for doc in documents:
            result = self.extract(doc)
            for ent in result.get("entities", []):
                key = (ent.get("name", "").strip(), ent.get("type", "").strip())
                if key[0] and key not in merged_entities:
                    merged_entities[key] = {"name": key[0], "type": key[1]}
            for rel in result.get("relations", []):
                key = (
                    rel.get("source", "").strip(),
                    rel.get("target", "").strip(),
                    rel.get("type", "").strip(),
                )
                if key[0] and key[1] and key not in merged_relations:
                    merged_relations[key] = {
                        "source": key[0],
                        "target": key[1],
                        "type": key[2],
                    }

        return {
            "entities": [
                {"name": name, "type": etype} for (name, etype) in merged_entities
            ],
            # 组织成与 structured 模式一致的三元组结构
            "relations": [
                {"source": s, "target": t, "type": rtype}
                for (s, t, rtype) in merged_relations
            ],
        }
