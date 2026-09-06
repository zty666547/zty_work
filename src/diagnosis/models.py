"""主动诊断过程中的稳定数据契约。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from uuid import uuid4


@dataclass
class DiagnosisState:
    report: str
    issue_name: str
    probabilities: dict[str, float]
    session_id: str = field(default_factory=lambda: uuid4().hex[:12])
    asked_questions: list[str] = field(default_factory=list)
    answers: dict[str, str] = field(default_factory=dict)
    status: str = "questioning"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> "DiagnosisState":
        return cls(**value)


@dataclass(frozen=True)
class QuestionChoice:
    name: str
    text: str
    yes_label: str
    no_label: str
    information_gain: float
    utility: float
    reason: str


@dataclass(frozen=True)
class PlanItem:
    cause: str
    probability: float
    check: str
    command: str
    repair: str
    risk: str
    risk_level: str
    blocked: bool
    sources: tuple[dict, ...]
