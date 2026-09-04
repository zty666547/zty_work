"""Prompt 模板：集中管理，便于统一修改与答辩讲解。"""
from __future__ import annotations

RAG_SYSTEM_PROMPT = """你是一个严谨的培养方案与选课规则问答助手。当前知识库以天津大学《2024级人工智能专业培养方案》为主，并包含带来源和适用范围的规则资料。你只能依据下面提供的【知识图谱上下文】回答问题。

规则：
1. 先给一句话结论，再说明概念或规则；在相关事实后引用证据编号，例如 [E1]。
2. 如果上下文里没有答案，请明确说明“根据当前知识图谱无法回答”，不要编造。
3. 不要把 2024 级规则泛化到其他年级；回答默认使用中文，保持条理清晰。
4. 不要推断上下文中没有给出的先修关系或实时开课信息。
5. 明确区分文件中的事实、从字段关系得到的解释和操作建议。
6. 必须关注证据里的 scope、source_tier 与 verification_status；学期性规则不得泛化到其他学期。
7. 如果证据标记“待原始通知复核”，必须在答案中提示该结论仍需以教务系统或官方原文为准。"""


def build_rag_user_prompt(
    question: str,
    context_text: str,
    source_title: str = "天津大学《2024级人工智能专业培养方案》",
) -> str:
    """构造 RAG 问答的用户提示。"""
    return f"""【资料来源】
{source_title}

【知识图谱上下文】
{context_text}

【用户问题】
{question}

请基于上述上下文回答，并使用 [E1] 形式标注依据。#"""


def build_context_text(triples: list[dict]) -> str:
    """把三元组列表渲染成人类可读 / 模型可读的文本。"""
    if not triples:
        return "（无相关图谱内容）"
    lines = []
    for t in triples:
        src = t.get("source", "")
        rel = t.get("rel", "")
        dst = t.get("target", "")
        source_props = _display_props(t.get("source_props") or {})
        relation_props = _display_props(t.get("rel_props") or {})
        target_props = _display_props(t.get("target_props") or {})
        evidence_id = t.get("evidence_id", f"E{len(lines) + 1}")
        lines.append(
            f"[{evidence_id}] {src}{source_props}  "
            f"{rel}{relation_props}  {dst}{target_props}"
        )
    return "\n".join(lines)


def _display_props(props: dict) -> str:
    """把有答辩价值的属性稳定地渲染到检索上下文。"""
    hidden = {"name", "created_at", "aliases"}
    items = [
        f"{key}={value}"
        for key, value in sorted(props.items())
        if key not in hidden and value not in (None, "", [])
    ]
    return f"（{', '.join(items)}）" if items else ""
