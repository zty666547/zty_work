"""把候选原因转换为带前置条件、风险和来源的排查计划。"""
from __future__ import annotations

from collections import defaultdict

from src.data.loader import StructuredGraph
from src.diagnosis.models import DiagnosisState, PlanItem


DANGEROUS_COMMAND_MARKERS = ("rm -rf", "sudo rm", "format ", "del /s", "chmod -r 777")


class PlanBuilder:
    def __init__(self, graph: StructuredGraph):
        self.nodes: dict[str, dict] = {}
        for items in graph.entities.values():
            for item in items:
                self.nodes[item["name"]] = dict(item.get("props") or {})
        self.relations: dict[str, list[dict]] = defaultdict(list)
        for row in graph.relations:
            self.relations[row["type"]].append(row)

    def _targets(self, relation_type: str, source: str) -> list[str]:
        return [row["target"] for row in self.relations[relation_type] if row["source"] == source]

    def _sources(self, node: str) -> tuple[dict, ...]:
        supported_types = {"CAUSE_SUPPORTED_BY", "CHECK_SUPPORTED_BY", "REPAIR_SUPPORTED_BY"}
        names = {
            row["target"]
            for relation_type in supported_types
            for row in self.relations[relation_type]
            if row["source"] == node
        }
        return tuple(
            {"title": name, **self.nodes[name]}
            for name in sorted(names)
        )

    def build(self, state: DiagnosisState, platform: str = "macos", limit: int = 3) -> list[PlanItem]:
        ranked = sorted(state.probabilities.items(), key=lambda item: (-item[1], item[0]))[:limit]
        result: list[PlanItem] = []
        for cause, probability in ranked:
            checks = self._targets("CAUSE_CHECKED_BY", cause)
            repairs = self._targets("CAUSE_RESOLVED_BY", cause)
            if not checks or not repairs:
                continue
            check, repair = checks[0], repairs[0]
            required = self._targets("REPAIR_REQUIRES", repair)
            risks = self._targets("REPAIR_HAS_RISK", repair)
            risk_name = risks[0] if risks else "未标注风险"
            risk_level = self.nodes.get(risk_name, {}).get("level", "unknown")
            command = self.nodes[check].get(f"command_{platform}", "")
            repair_text = self.nodes[repair].get(f"instruction_{platform}") or self.nodes[repair].get("instruction", "")
            sources = tuple({item["title"]: item for item in (*self._sources(cause), *self._sources(check), *self._sources(repair))}.values())
            blocked = (
                risk_level == "high"
                or check not in required
                or not sources
                or any(marker in f"{command} {repair_text}".casefold() for marker in DANGEROUS_COMMAND_MARKERS)
            )
            result.append(
                PlanItem(
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
            )
        return result


def verify_plan(items: list[PlanItem]) -> list[str]:
    errors: list[str] = []
    for item in items:
        if not item.check:
            errors.append(f"{item.cause} 缺少前置检查")
        if not item.sources:
            errors.append(f"{item.cause} 缺少来源")
        if item.risk_level not in {"low", "medium", "high"}:
            errors.append(f"{item.cause} 风险等级无效")
        if item.risk_level == "high" and not item.blocked:
            errors.append(f"{item.cause} 高风险操作未被阻止")
    return errors
