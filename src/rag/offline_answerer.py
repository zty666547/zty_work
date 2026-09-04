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
    "HAS_RULE": "适用规则",
    "GOVERNS_CATEGORY": "约束课程类别",
    "GOVERNS_GROUP": "约束课程组",
    "GOVERNS_CONCEPT": "解释概念",
    "ALLOWS_OPTION": "允许选择",
    "SUPPORTED_BY": "依据来源",
    "CATEGORY_IN_DOMAIN": "所属培养领域",
    "HAS_NATURE": "修读性质",
    "CONTAINS_GROUP": "包含课程组",
    "COUNTS_TOWARD": "计入",
    "DEFINED_BY": "定义依据",
}


def _node_props(triples: list[dict]) -> dict[str, dict]:
    """从检索三元组中收集节点属性。"""
    nodes: dict[str, dict] = {}
    for triple in triples:
        nodes[triple["source"]] = triple.get("source_props") or {}
        nodes[triple["target"]] = triple.get("target_props") or {}
    return nodes


def _citations(triples: list[dict], limit: int = 6) -> str:
    return "".join(
        f"[{triple.get('evidence_id') or f'E{index}'}]"
        for index, triple in enumerate(triples[:limit], start=1)
    )


def _rule_priority(question: str, props: dict) -> int:
    """按问题关键词挑选最相关规则，避免把相邻规则全部堆进答案。"""
    text = str(props.get("name", "")) + str(props.get("statement", ""))
    score = 0
    keyword_groups = [
        (("四史", "习近平"), "course_group_requirement"),
        (("建议修读", "建议学期", "推荐学期"), "recommendation"),
        (("文化素质", "通识", "校任选"), "minimum_credits"),
        (("专业选修",), "minimum_credits"),
        (("跨年级", "跨专业", "计划外"), "semester_operation"),
    ]
    for keywords, rule_type in keyword_groups:
        if any(keyword in question for keyword in keywords):
            if props.get("rule_type") == rule_type:
                score += 4
            score += sum(keyword in text for keyword in keywords)
    return score


def _trim_sentence(value: str) -> str:
    return value.rstrip("。；; ")


def build_offline_answer(question: str, triples: list[dict]) -> str:
    """把已召回三元组转成自然语言答案，并明确知识边界。"""
    refusal = scope_refusal(question)
    if refusal:
        return refusal
    if not triples:
        return "根据当前收录的 2024 级人工智能专业培养方案，暂时无法回答这个问题。"

    nodes = _node_props(triples)
    citations = _citations(triples)

    rules = [
        {"name": name, **props}
        for name, props in nodes.items()
        if props.get("entity_type") == "Rule"
    ]
    if rules:
        ranked = sorted(
            rules,
            key=lambda props: (-_rule_priority(question, props), props["name"]),
        )
        best_score = _rule_priority(question, ranked[0])
        selected = [
            rule
            for rule in ranked
            if _rule_priority(question, rule) == best_score
        ][:2]
        statements = [
            _trim_sentence(rule.get("statement", rule["name"]))
            for rule in selected
        ]
        status_notes = sorted(
            {
                rule["verification_status"]
                for rule in selected
                if rule.get("verification_status")
            }
        )
        answer = "结论：" + "；".join(statements) + f"。{citations}"
        if status_notes:
            answer += "\n\n证据状态：" + "；".join(status_notes) + "。"
        return answer

    if "选修" in question and "通识" in question and {
        "通识教育",
        "选修课程性质",
    }.issubset(nodes):
        return (
            "结论：“通识”描述课程所属的培养领域，“选修”描述课程的修读性质，"
            "二者不是同一个分类维度。文化素质选修课既属于通识教育领域，"
            f"又具有选修性质；通识教育中也存在必修模块。{citations}"
        )

    if "专业核心课" in nodes and "专业选修课" in nodes:
        core_credits = nodes["专业核心课"].get("required_credits", 21)
        elective_credits = nodes["专业选修课"].get("required_credits", 16)
        return (
            "结论：两者都属于专业教育，但修读性质不同。"
            f"专业核心课是培养方案指定的必修模块，共{core_credits}学分；"
            f"专业选修课允许从课程清单中选择，但累计须完成{elective_credits}学分。"
            f"{citations}"
        )

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
