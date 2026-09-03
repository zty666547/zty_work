"""Graph RAG 问答链路：检索 + 生成。"""
from __future__ import annotations

import logging

from config.settings import Settings
from src.extraction.llm_client import LLMClient
from src.graph.neo4j_client import Neo4jClient
from src.rag.prompts import RAG_SYSTEM_PROMPT, build_rag_user_prompt
from src.rag.retriever import GraphRetriever
from src.utils.logger import get_logger

logger = get_logger("kg_rag.chain")


class GraphRAGChain:
    """把检索器与生成模型串成一条可复用链路。

    query -> 图检索(召回/扩展/组装) -> LLM 生成。
    """

    def __init__(self, settings: Settings, client: Neo4jClient, llm: LLMClient):
        self.settings = settings
        self.retriever = GraphRetriever(client)
        self.llm = llm

    def answer(self, question: str, hop: int = 2, show_context: bool = False) -> dict:
        """回答一个问题，返回答案及中间上下文（便于调试/演示）。"""
        retrieved = self.retriever.retrieve(question, hop=hop)
        context_text = retrieved["context_text"]
        user_prompt = build_rag_user_prompt(question, context_text)
        answer = self.llm.chat(RAG_SYSTEM_PROMPT, user_prompt, temperature=0.2)
        logger.info("RAG 答案生成完成")

        result = {
            "question": question,
            "answer": answer,
            "entities": retrieved["entities"],
            "triples": retrieved["triples"],
            "context_text": context_text,
        }
        if show_context:
            print("\n=== 检索上下文（知识图谱子图）===")
            print(context_text)
            print("=" * 40 + "\n")
        return result
