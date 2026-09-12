"""可复现实验使用的主动诊断选问策略。"""
from __future__ import annotations

import random
from typing import Protocol

from src.diagnosis.engine import DiagnosisEngine
from src.diagnosis.models import DiagnosisState, QuestionChoice


class QuestionPolicy(Protocol):
    name: str

    def choose(
        self, engine: DiagnosisEngine, state: DiagnosisState
    ) -> QuestionChoice | None: ...


class DirectPolicy:
    """不追问，直接按先验概率给出原因排序。"""

    name = "direct"

    def choose(self, engine: DiagnosisEngine, state: DiagnosisState) -> None:
        return None


class FixedOrderPolicy:
    """按知识库中的固定顺序提问。"""

    name = "fixed_order"

    def choose(
        self, engine: DiagnosisEngine, state: DiagnosisState
    ) -> QuestionChoice | None:
        choices = engine.available_questions(state)
        return choices[0] if choices else None


class RandomPolicy:
    """从剩余问题中随机选择；随机源由调用方注入以确保可复现。"""

    name = "random_question"

    def __init__(self, seed: int = 0):
        self._random = random.Random(seed)

    def choose(
        self, engine: DiagnosisEngine, state: DiagnosisState
    ) -> QuestionChoice | None:
        choices = engine.available_questions(state)
        return self._random.choice(choices) if choices else None


class InformationGainPolicy:
    """选择综合效用最高的问题，即系统当前采用的完整方法。"""

    name = "information_gain"

    def choose(
        self, engine: DiagnosisEngine, state: DiagnosisState
    ) -> QuestionChoice | None:
        return engine.next_question(state)


class PureInformationGainPolicy:
    """只按原始信息增益选问，不使用可回答率、成本或风险修正。"""

    name = "pure_information_gain"

    def choose(
        self, engine: DiagnosisEngine, state: DiagnosisState
    ) -> QuestionChoice | None:
        choices = engine.available_questions(state, answerability_aware=False)
        if not choices:
            return None
        best = max(choices, key=lambda item: (item.information_gain, item.name))
        if best.information_gain < engine.settings.min_information_gain:
            return None
        return best
