"""知识库版本范围检查。"""
from __future__ import annotations

import re


SUPPORTED_COHORT = "2023"
SOURCE_NAME = "天津大学《2023级人工智能专业培养方案》"


def unsupported_cohorts(question: str) -> list[str]:
    """返回问题中出现、但当前知识库不支持的入学年级。"""
    cohorts = re.findall(r"(20\d{2})\s*级", question)
    return sorted({cohort for cohort in cohorts if cohort != SUPPORTED_COHORT})


def scope_refusal(question: str) -> str | None:
    cohorts = unsupported_cohorts(question)
    if not cohorts:
        return None
    requested = "、".join(f"{cohort}级" for cohort in cohorts)
    return (
        f"当前知识库只收录 2023 级人工智能专业培养方案，无法可靠回答{requested}的问题。"
        "请查阅对应年级的正式培养方案。"
    )

