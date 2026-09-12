"""根据服务与部署上下文选择具体检查和修复。"""
from __future__ import annotations

from src.diagnosis.models import DiagnosisState, PlanItem
from src.diagnosis.planner import DANGEROUS_COMMAND_MARKERS, PlanBuilder


class PlanBuilderV2(PlanBuilder):
    def build(
        self,
        state: DiagnosisState,
        platform: str = "macos",
        limit: int = 3,
        context: str | None = None,
    ) -> list[PlanItem]:
        items = super().build(state, platform=platform, limit=limit)
        if not context:
            return items

        ranked = sorted(
            state.probabilities.items(),
            key=lambda item: (-item[1], item[0]),
        )[:limit]
        contextual_causes = {
            row["source"]
            for row in self.relations["CAUSE_CONTEXTUALIZED_BY"]
            if row["target"] == context
        }
        checks = self._targets("CONTEXT_CHECKED_BY", context)
        repairs = self._targets("CONTEXT_RESOLVED_BY", context)
        if not contextual_causes or not checks or not repairs:
            return items

        check, repair = checks[0], repairs[0]
        required = self._targets("REPAIR_REQUIRES", repair)
        risks = self._targets("REPAIR_HAS_RISK", repair)
        risk_name = risks[0] if risks else "未标注风险"
        risk_level = self.nodes.get(risk_name, {}).get("level", "unknown")
        command = self.nodes[check].get(f"command_{platform}", "")
        repair_text = self.nodes[repair].get(f"instruction_{platform}") or self.nodes[
            repair
        ].get("instruction", "")
        sources = tuple(
            {
                item["title"]: item
                for item in (*self._sources(check), *self._sources(repair))
            }.values()
        )
        blocked = (
            risk_level == "high"
            or check not in required
            or not sources
            or any(
                marker in f"{command} {repair_text}".casefold()
                for marker in DANGEROUS_COMMAND_MARKERS
            )
        )

        replacement_by_cause = {
            cause: PlanItem(
                cause=cause,
                probability=probability,
                check=self.nodes[check].get("description", check),
                command=command,
                repair=repair_text,
                risk=risk_name,
                risk_level=risk_level,
                blocked=blocked,
                sources=sources,
            )
            for cause, probability in ranked
            if cause in contextual_causes
        }
        return [replacement_by_cause.get(item.cause, item) for item in items]
