"""Prompt 模板：集中管理，便于统一修改与答辩讲解。"""
from __future__ import annotations

RAG_SYSTEM_PROMPT = """你是一个严谨的知识问答助手。你只能依据下面提供的【知识图谱上下文】回答问题。

规则：
1. 如果上下文里有答案，请直接、简洁、准确地回答，并尽量引用图谱中的实体与关系。
2. 如果上下文里没有答案，请明确说明“根据当前知识图谱无法回答”，不要编造。
3. 回答默认使用中文，保持条理清晰。"""


def build_rag_user_prompt(question: str, context_text: str) -> str:
    """构造 RAG 问答的用户提示。"""
    return f"""【知识图谱上下文】
{context_text}

【用户问题】
{question}

请基于上述上下文回答。#"""


def build_context_text(triples: list[dict]) -> str:
    """把三元组列表渲染成人类可读 / 模型可读的文本。"""
    if not triples:
        return "（无相关图谱内容）"
    lines = []
    for t in triples:
        src = t.get("source", "")
        rel = t.get("rel", "")
        dst = t.get("target", "")
        lines.append(f"- {src}  {rel}  {dst}")
    return "\n".join(lines)
