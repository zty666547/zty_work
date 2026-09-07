"""面向 CLI、网页和测试的统一诊断服务。"""
from __future__ import annotations

from pathlib import Path
from copy import deepcopy

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
        self._record(state, "initial")
        return self.snapshot(state)

    def answer(self, state_value: dict, question_name: str, answer: str) -> dict:
        state = DiagnosisState.from_dict(deepcopy(state_value))
        choice = next((q for q in self.engine.available_questions(state) if q.name == question_name), None)
        self.engine.answer(state, question_name, answer)
        self._record(state, "answer", choice.__dict__ if choice else None, answer)
        return self.snapshot(state)

    def complete(self, state_value: dict) -> dict:
        state = DiagnosisState.from_dict(deepcopy(state_value))
        if state.status == "completed":
            return self.snapshot(state)
        state.status = "completed"
        state.stop_reason = "用户主动结束追问"
        self._record(state, "manual_stop")
        return self.snapshot(state)

    def _record(self, state: DiagnosisState, event: str, question: dict | None = None, answer: str | None = None) -> None:
        """保存不可变的阶段快照；页面重绘不新增轨迹。"""
        next_question = self.engine.next_question(state)
        state.trajectory.append(deepcopy({
            "step": len(state.trajectory), "round": len(state.asked_questions),
            "event": event, "issue_name": state.issue_name,
            "question": question, "answer": answer,
            "observation": self.engine.question_observation.get(question["name"]) if question else None,
            "candidates": self.engine.ranked_candidates(state),
            "entropy": self.engine.entropy(state),
            "next_question": next_question.__dict__ if next_question else None,
            "status": state.status, "stop_reason": state.stop_reason,
        }))

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
