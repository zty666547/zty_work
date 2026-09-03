"""基于检索证据生成可读的离线答案，不依赖外部大模型。"""
from __future__ import annotations

from collections import defaultdict

from src.rag.scope import scope_refusal


RELATION_LABELS = {
    "BELONGS_TO_CATEGORY": "课程类别",
    "OFFERED_IN": "建议学期",
    "TAUGHT_BY": "开课单位",
    "HAS_COURSE": "包含课程",
    "HAS_REQUIREMENT": "毕业要求",
    "SUPPORTS_REQUIREMENT": "支撑毕业要求",
}


def build_offline_answer(question: str, triples: list[dict]) -> str:
    """把已召回三元组转成自然语言答案，并明确知识边界。"""
    refusal = scope_refusal(question)
    if refusal:
        return refusal
    if not triples:
        return "根据当前收录的 2023 级人工智能专业培养方案，暂时无法回答这个问题。"

    facts_by_course: dict[str, dict] = defaultdict(dict)
    requirements: list[str] = []
    for triple in triples:
        source = triple["source"]
        target = triple["target"]
        relation = triple["rel"]
        source_props = triple.get("source_props") or {}
        if source_props.get("entity_type") == "Course":
            facts_by_course[source].update(source_props)
            facts_by_course[source][relation] = target
        if relation == "HAS_REQUIREMENT":
            requirements.append(target)

    citations = "".join(
        f"[{triple.get('evidence_id') or f'E{index}'}]"
        for index, triple in enumerate(triples[:6], start=1)
    )

    if requirements:
        return (
            "该培养方案列出的毕业要求包括："
            + "、".join(sorted(set(requirements)))
            + f"。{citations}"
        )

    course_lines = []
    for course, facts in sorted(facts_by_course.items()):
        details = []
        if "credits" in facts:
            details.append(f"{facts['credits']} 学分")
        if "OFFERED_IN" in facts:
            details.append(f"建议在{facts['OFFERED_IN']}修读")
        if "BELONGS_TO_CATEGORY" in facts:
            details.append(f"属于{facts['BELONGS_TO_CATEGORY']}")
        if "TAUGHT_BY" in facts:
            details.append(f"由{facts['TAUGHT_BY']}开课")
        course_lines.append(f"{course}（{'，'.join(details)}）" if details else course)

    if course_lines:
        return "根据培养方案，" + "；".join(course_lines) + f"。{citations}"

    rendered = []
    for triple in triples[:12]:
        label = RELATION_LABELS.get(triple["rel"], triple["rel"])
        rendered.append(f"{triple['source']}的{label}是{triple['target']}")
    return "根据培养方案，" + "；".join(rendered) + f"。{citations}"
