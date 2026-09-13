"""从固定轨迹提取可核对的算法讲解数据。"""
from __future__ import annotations

from typing import Any
import json


def build_algorithm_explanation(demo: dict[str, Any], settings) -> dict[str, Any]:
    stages = demo["trajectory"]
    if len(stages) != 3:
        raise ValueError("固定案例必须包含三个阶段")
    initial, first_answer, final = stages
    question = initial["next_question"]
    calculated_utility = (
        question["information_gain"] * question["answerability"]
        - settings.question_cost_weight * question["cost"]
        - settings.question_risk_weight * question["risk_cost"]
    )
    observation = first_answer["observation"]
    likelihood_edge = next(
        edge
        for edge in demo["subgraphs"][1]["edges"]
        if edge["source"] == observation
        and edge["target"] == first_answer["candidates"][0]["name"]
        and edge["type"] == "OBSERVATION_SUPPORTS"
    )
    top_initial = initial["candidates"][0]
    top_after_first = first_answer["candidates"][0]
    top_final = final["candidates"][0]
    return {
        "retrieval": {
            "cause": top_initial["name"],
            "probability": top_initial["probability"],
            "candidate_count": len(initial["candidates"]),
            "evidence": [
                item["name"]
                for item in demo["routing"]["candidates"][0]["evidence"]
            ],
        },
        "question_selection": {
            "question": question["text"],
            "information_gain": question["information_gain"],
            "answerability": question["answerability"],
            "cost": question["cost"],
            "risk_cost": question["risk_cost"],
            "utility": question["utility"],
            "calculated_utility": calculated_utility,
        },
        "probability_update": {
            "answer": question[first_answer["answer"] + "_label"],
            "observation": observation,
            "p_observation_given_top_cause": likelihood_edge["props"][
                "p_yes_given_cause"
            ],
            "before": top_initial["probability"],
            "after_first": top_after_first["probability"],
            "initial_entropy": initial["entropy"],
            "after_first_entropy": first_answer["entropy"],
        },
        "stopping": {
            "final_probability": top_final["probability"],
            "margin": demo["final"]["decision"]["margin"],
            "informative_answers": demo["final"]["decision"][
                "informative_answers"
            ],
            "confidence_threshold": settings.confidence_threshold,
            "margin_threshold": settings.confidence_margin,
            "minimum_answers": settings.min_informative_answers,
            "stop_reason": demo["final"]["stop_reason"],
        },
    }


def injection_flow_dot() -> str:
    """知识注入只保留一条可验证的约束链。"""
    nodes = [
        ("graph", "① 图谱推理结果\n原因、概率、来源", "#dbeafe"),
        ("plan", "② 已验证方案\n检查、修复、风险", "#bbf7d0"),
        ("manifest", "③ 声明/证据白名单\nC1… + E031…", "#fef08a"),
        ("llm", "④ DeepSeek只负责\n排序与表达侧重", "#ddd6fe"),
        ("guard", "⑤ 程序校验\n合法输出或离线回退", "#fecaca"),
    ]
    q = lambda value: json.dumps(value, ensure_ascii=False)
    lines = [
        "digraph Injection {", "rankdir=LR;",
        'graph [bgcolor="transparent", nodesep=0.35, ranksep=0.45];',
        'node [shape=box, style="rounded,filled", fontname="Arial", fontsize=10, color="#64748b"];',
        'edge [fontname="Arial", fontsize=9, color="#64748b"];',
    ]
    for name, label, color in nodes:
        lines.append(f"{q(name)} [label={q(label)}, fillcolor={q(color)}];")
    for source, target, label in [
        ("graph", "plan", "构建并验证"),
        ("plan", "manifest", "编号和约束"),
        ("manifest", "llm", "只传允许内容"),
        ("llm", "guard", "只接收JSON决策"),
    ]:
        lines.append(f"{q(source)} -> {q(target)} [label={q(label)}];")
    lines.append("}")
    return "\n".join(lines)
