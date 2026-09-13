"""第二版问题效用参数的真实观察记录与保守校准。"""
from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any, Iterable

from src.diagnosis.case_export import build_case_export


def build_case_export_v2(
    snapshot: dict[str, Any],
    actual_cause: str | None = None,
    confirmed: bool = False,
    note: str = "",
) -> dict[str, Any]:
    """扩展案例导出，保留问题回答结果和页面观测耗时。"""
    exported = build_case_export(
        snapshot,
        actual_cause=actual_cause,
        confirmed=confirmed,
        note=note,
    )
    observations = []
    for stage in snapshot["state"].get("trajectory", []):
        question = stage.get("question")
        answer = stage.get("answer")
        if not question or answer not in {"yes", "no", "unknown"}:
            continue
        feedback = stage.get("feedback") or {}
        seconds = feedback.get("response_seconds")
        observations.append(
            {
                "question": question["name"],
                "answer": answer,
                "informative": answer != "unknown",
                "response_seconds": (
                    round(float(seconds), 3) if seconds is not None else None
                ),
                "recorded_by": feedback.get("recorded_by", "not_recorded"),
            }
        )
    exported["schema_version"] = "debugpath-case-v2"
    exported["question_observations"] = observations
    return exported


def calibrate_question_observations(
    cases: Iterable[dict[str, Any]],
    *,
    minimum_samples: int = 5,
    prior_successes: float = 1.0,
    prior_failures: float = 1.0,
) -> dict[str, Any]:
    """汇总真实观测；样本不足时只报告，不产生参数替换建议。"""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    case_count = 0
    for case in cases:
        case_count += 1
        for item in case.get("question_observations", []):
            if item.get("answer") not in {"yes", "no", "unknown"}:
                continue
            grouped[str(item["question"])].append(item)

    questions = []
    for name in sorted(grouped):
        items = grouped[name]
        informative = sum(item["answer"] != "unknown" for item in items)
        timed = [
            float(item["response_seconds"])
            for item in items
            if item.get("response_seconds") is not None
            and 0 <= float(item["response_seconds"]) <= 3600
        ]
        sample_count = len(items)
        smoothed = (
            informative + prior_successes
        ) / (sample_count + prior_successes + prior_failures)
        enough = sample_count >= minimum_samples
        median_seconds = median(timed) if timed else None
        if enough and median_seconds is not None:
            recommended_cost = 1 if median_seconds <= 30 else (2 if median_seconds <= 90 else 3)
        else:
            recommended_cost = None
        questions.append(
            {
                "question": name,
                "samples": sample_count,
                "informative_answers": informative,
                "unknown_rate": round(1 - informative / sample_count, 6),
                "timed_samples": len(timed),
                "median_response_seconds": (
                    round(median_seconds, 3) if median_seconds is not None else None
                ),
                "eligible_for_recommendation": enough,
                "recommended_answerability": round(smoothed, 6) if enough else None,
                "recommended_cost": recommended_cost,
            }
        )

    return {
        "schema_version": "debugpath-question-calibration-v1",
        "case_count": case_count,
        "minimum_samples_per_question": minimum_samples,
        "method": {
            "answerability": "Beta(1,1)平滑后的非unknown回答比例",
            "cost": "回答中位耗时：不超过30秒为1，30至90秒为2，超过90秒为3",
            "risk": "不从回答耗时推断，必须由安全审查单独标注",
        },
        "questions": questions,
        "warning": "输出仅为参数建议；人工复核并冻结新版本前不会修改图谱。",
    }
