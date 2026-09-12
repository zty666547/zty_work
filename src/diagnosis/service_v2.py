"""第二版诊断入口；与已冻结的第一版服务并行存在。"""
from __future__ import annotations

from pathlib import Path

from config.settings import Settings
from src.diagnosis.engine import UnknownIssueError
from src.diagnosis.models import DiagnosisState
from src.diagnosis.service import DiagnosisService
from src.retrieval.issue_router import IssueRouter


class AmbiguousIssueError(ValueError):
    """多个故障族接近，需要用户先澄清。"""

    def __init__(self, decision: dict):
        super().__init__(decision["clarification"])
        self.decision = decision


class DiagnosisServiceV2(DiagnosisService):
    """先执行可解释故障族检索，再复用第一版动态诊断链。"""

    def __init__(
        self,
        settings: Settings | None = None,
        knowledge_path: Path | None = None,
    ):
        super().__init__(settings=settings, knowledge_path=knowledge_path)
        self.issue_router = IssueRouter(self.graph)

    def start(self, report: str) -> dict:
        report = report.strip()
        if not report:
            raise ValueError("故障描述不能为空")
        routing = self.issue_router.decide(report)
        if routing["status"] == "unsupported":
            raise UnknownIssueError("当前证据不足以识别故障族，请补充组件和完整报错")
        if routing["status"] == "ambiguous":
            raise AmbiguousIssueError(routing)

        issue_name = routing["selected_issue"]
        causes = self.engine.issue_causes[issue_name]
        probabilities = {
            item["name"]: float(item.get("prior", 1.0)) for item in causes
        }
        self.engine._normalize(probabilities)
        state = DiagnosisState(
            report=report,
            issue_name=issue_name,
            probabilities=probabilities,
        )
        hits = (
            self.retriever.search(report, top_k=self.settings.evidence_top_k)
            if self.settings.enable_evidence_retrieval
            else []
        )
        self.retriever.apply_to_state(
            state,
            hits,
            weight=self.settings.evidence_weight,
        )
        self._record(state, "initial")
        snapshot = self.snapshot(state)
        snapshot["routing"] = routing
        return snapshot
