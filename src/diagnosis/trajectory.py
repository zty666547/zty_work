"""诊断阶段的可回放图谱视图，仅显示知识库中存在的边。"""
from __future__ import annotations

import json


def stage_dot(stage: dict, graph, previous: dict | None = None) -> str:
    probabilities = {c["name"]: c["probability"] for c in stage["candidates"]}
    before = {c["name"]: c["probability"] for c in (previous or stage)["candidates"]}
    question = stage.get("question") or stage.get("next_question")
    selected = {stage["issue_name"], *probabilities}
    if question:
        selected.add(question["name"])
    if stage.get("observation"):
        selected.add(stage["observation"])
    top = stage["candidates"][0]["name"]
    if stage["status"] == "completed":
        selected.update(r["target"] for r in graph.relations if r["source"] == top and r["type"] in {"CAUSE_CHECKED_BY", "CAUSE_RESOLVED_BY", "CAUSE_SUPPORTED_BY"})
        for _ in range(2):
            selected.update(r["target"] for r in graph.relations if r["source"] in selected and r["type"] in {"REPAIR_REQUIRES", "REPAIR_HAS_RISK", "CHECK_SUPPORTED_BY", "REPAIR_SUPPORTED_BY"})
    nodes = {n["name"]: (kind, n.get("props", {})) for kind, items in graph.entities.items() for n in items}
    q = lambda value: json.dumps(value, ensure_ascii=False)
    lines = ['digraph G {', 'rankdir=LR;', 'node [shape=ellipse, style=filled, fontname="Arial"];']
    colors = {"Issue": "#bfdbfe", "DiagnosticQuestion": "#ddd6fe", "Observation": "#a5f3fc"}
    for name in sorted(selected):
        kind, props = nodes[name]
        label, color, width = name, colors.get(kind, "#bbf7d0"), 1.2
        if name in probabilities:
            p = probabilities[name]
            label = f"{name}\n{p:.1%}"
            color = "#e5e7eb" if p < before.get(name, p) - 1e-9 else "#fef08a"
            width = 1.2 + p * 1.5
            if name == top:
                label += "\n当前首位"
                color = "#86efac"
        elif kind == "DiagnosticQuestion":
            label = props.get("text", name)
        elif name == stage.get("observation"):
            label += "\n" + {"yes": "用户确认：是", "no": "用户确认：否", "unknown": "用户暂时无法确认"}[stage["answer"]]
        lines.append(f'{q(name)} [label={q(label)}, fillcolor={q(color)}, width={width:.2f}];')
    labels = {"HAS_POSSIBLE_CAUSE": "可能原因", "HAS_QUESTION": "诊断问题", "CHECKS": "检查观察", "OBSERVATION_SUPPORTS": "条件概率关系", "CAUSE_CHECKED_BY": "检查", "CAUSE_RESOLVED_BY": "修复", "REPAIR_REQUIRES": "前置检查", "REPAIR_HAS_RISK": "风险", "CAUSE_SUPPORTED_BY": "来源", "CHECK_SUPPORTED_BY": "来源", "REPAIR_SUPPORTED_BY": "来源"}
    for edge in graph.relations:
        if edge["source"] in selected and edge["target"] in selected:
            lines.append(f'{q(edge["source"])} -> {q(edge["target"])} [label={q(labels.get(edge["type"], edge["type"]))}];')
    lines.append("}")
    return "\n".join(lines)
