"""第二版诊断入口；与已冻结的第一版服务并行存在。"""
from __future__ import annotations

from pathlib import Path
from copy import deepcopy

from config.settings import Settings
from src.data.loader_v2 import load_v2_knowledge_base
from src.diagnosis.engine import DiagnosisEngine, UnknownIssueError
from src.diagnosis.models import DiagnosisState
from src.diagnosis.planner_v2 import PlanBuilderV2
from src.diagnosis.planner import verify_plan
from src.diagnosis.service import DiagnosisService
from src.retrieval.bm25 import EvidenceRetriever
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
        primary_path = knowledge_path or (
            self.settings.raw_dir / self.settings.structured_filename
        )
        evidence_path = primary_path.parent / self.settings.evidence_filename
        overlay_path = self.settings.raw_dir / "debugpath_v2_service_context.json"
        self.graph = load_v2_knowledge_base(
            primary_path,
            evidence_path,
            overlay_path,
        )
        self.engine = DiagnosisEngine(self.graph, self.settings)
        self.planner = PlanBuilderV2(self.graph)
        self.retriever = EvidenceRetriever(self.graph)
        self.issue_router = IssueRouter(self.graph)
        self._routing_by_session: dict[str, dict] = {}
        self._context_by_session: dict[str, str | None] = {}

    @staticmethod
    def _detect_context(report: str) -> str | None:
        normalized = report.casefold()
        has_open_webui = "open webui" in normalized or "openwebui" in normalized
        if "ollama" in normalized and has_open_webui and (
            "docker" in normalized or "容器" in normalized
        ):
            return "Open WebUI容器访问宿主机Ollama"
        return None

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
        self._routing_by_session[state.session_id] = deepcopy(routing)
        self._context_by_session[state.session_id] = self._detect_context(report)
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
        return self.snapshot(state)

    def _record(
        self,
        state: DiagnosisState,
        event: str,
        question: dict | None = None,
        answer: str | None = None,
    ) -> None:
        super()._record(state, event, question, answer)
        state.trajectory[-1]["routing"] = deepcopy(
            self._routing_by_session.get(state.session_id)
        )
        state.trajectory[-1]["service_context"] = self._context_by_session.get(
            state.session_id
        )

    def snapshot(self, state: DiagnosisState, platform: str | None = None) -> dict:
        platform = platform or self.settings.platform
        snapshot = super().snapshot(state, platform=platform)
        context = self._context_by_session.get(state.session_id)
        plan = self.planner.build(state, platform=platform, context=context)
        snapshot["plan"] = [item.__dict__ for item in plan]
        snapshot["plan_errors"] = verify_plan(plan)
        snapshot["routing"] = deepcopy(
            self._routing_by_session.get(state.session_id)
        )
        snapshot["service_context"] = context
        return snapshot
