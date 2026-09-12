"""第二版诊断引擎：只让当前部署上下文适用的问题参与选问。"""
from __future__ import annotations

from src.diagnosis.engine import DiagnosisEngine
from src.diagnosis.models import DiagnosisState, QuestionChoice


def detect_contexts(report: str) -> set[str]:
    normalized = report.casefold()
    has_open_webui = "open webui" in normalized or "openwebui" in normalized
    contexts = set()
    if "ollama" in normalized and has_open_webui and (
        "docker" in normalized or "容器" in normalized
    ):
        contexts.add("Open WebUI容器访问宿主机Ollama")
    return contexts


class DiagnosisEngineV2(DiagnosisEngine):
    def available_questions(
        self,
        state: DiagnosisState,
        answerability_aware: bool | None = None,
    ) -> list[QuestionChoice]:
        choices = super().available_questions(
            state,
            answerability_aware=answerability_aware,
        )
        contexts = detect_contexts(state.report)
        return [
            choice
            for choice in choices
            if not self.nodes[choice.name].get("required_context")
            or self.nodes[choice.name]["required_context"] in contexts
        ]
