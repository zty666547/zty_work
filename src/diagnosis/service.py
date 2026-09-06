"""面向 CLI、网页和测试的统一诊断服务。"""
from __future__ import annotations

from pathlib import Path

from config.settings import Settings
from src.data.loader import load_knowledge_base
from src.diagnosis.engine import DiagnosisEngine
from src.diagnosis.models import DiagnosisState
from src.diagnosis.planner import PlanBuilder, verify_plan
from src.retrieval.bm25 import EvidenceRetriever


class DiagnosisService:
    def __init__(self, settings: Settings | None = None, knowledge_path: Path | None = None):
        self.settings = settings or Settings()
        path = knowledge_path or self.settings.raw_dir / self.settings.structured_filename
        evidence_path = path.parent / self.settings.evidence_filename
        self.graph = load_knowledge_base(path, evidence_path)
        self.engine = DiagnosisEngine(self.graph, self.settings)
        self.planner = PlanBuilder(self.graph)
        self.retriever = EvidenceRetriever(self.graph)

    def start(self, report: str) -> dict:
        state = self.engine.start(report)
        hits = (
            self.retriever.search(report, top_k=self.settings.evidence_top_k)
            if self.settings.enable_evidence_retrieval
            else []
        )
        self.retriever.apply_to_state(state, hits, weight=self.settings.evidence_weight)
        return self.snapshot(state)

    def answer(self, state_value: dict, question_name: str, answer: str) -> dict:
        state = DiagnosisState.from_dict(state_value)
        self.engine.answer(state, question_name, answer)
        return self.snapshot(state)

    def complete(self, state_value: dict) -> dict:
        state = DiagnosisState.from_dict(state_value)
        state.status = "completed"
        return self.snapshot(state)

    def snapshot(self, state: DiagnosisState, platform: str | None = None) -> dict:
        platform = platform or self.settings.platform
        question = self.engine.next_question(state)
        plan = self.planner.build(state, platform=platform)
        return {
            "state": state.to_dict(),
            "candidates": self.engine.ranked_candidates(state),
            "question": question.__dict__ if question else None,
            "plan": [item.__dict__ for item in plan],
            "plan_errors": verify_plan(plan),
            "source": self.graph.source,
        }
