"""从固定轨迹提取可核对的算法讲解数据。"""
from __future__ import annotations

from typing import Any


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
