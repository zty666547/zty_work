"""DebugPath核心测试：不连接Neo4j，不调用大模型。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.settings import Settings
from src.data.loader import load_structured
from src.diagnosis.engine import DiagnosisEngine, UnknownIssueError
from src.diagnosis.generator import render_offline, render_with_llm
from src.diagnosis.models import DiagnosisState, PlanItem
from src.diagnosis.planner import PlanBuilder, verify_plan
from src.diagnosis.service import DiagnosisService

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE = ROOT / "data/raw/debugpath_knowledge.json"


@pytest.fixture(scope="module")
def service() -> DiagnosisService:
    return DiagnosisService(Settings())


def test_knowledge_graph_is_valid_and_substantial():
    graph = load_structured(KNOWLEDGE)
    assert sum(map(len, graph.entities.values())) >= 90
    assert len(graph.relations) >= 200
    assert len(graph.entities["Issue"]) == 3
    assert len(graph.entities["DocumentSource"]) >= 8


@pytest.mark.parametrize(
    ("report", "issue"),
    [
        ("ModuleNotFoundError: No module named x", "Python模块无法导入"),
        ("torch.cuda.is_available() False", "PyTorch无法使用GPU"),
        ("Neo4j Connection refused", "服务或配置连接失败"),
    ],
)
def test_issue_identification(service, report, issue):
    assert service.start(report)["state"]["issue_name"] == issue


def test_unknown_issue_is_explicit(service):
    with pytest.raises(UnknownIssueError):
        service.start("显示器颜色有一点奇怪")


def test_priors_are_normalized(service):
    snapshot = service.start("No module named pandas")
    assert sum(item["probability"] for item in snapshot["candidates"]) == pytest.approx(1.0)


def test_next_question_has_positive_information_gain(service):
    snapshot = service.start("No module named pandas")
    assert snapshot["question"]["information_gain"] > 0
    assert "不确定性" in snapshot["question"]["reason"]


def test_answer_changes_candidate_distribution(service):
    snapshot = service.start("No module named pandas")
    before = {item["name"]: item["probability"] for item in snapshot["candidates"]}
    snapshot = service.answer(snapshot["state"], snapshot["question"]["name"], "yes")
    after = {item["name"]: item["probability"] for item in snapshot["candidates"]}
    assert before != after
    assert sum(after.values()) == pytest.approx(1.0)


def test_unknown_answer_records_without_bayesian_update(service):
    snapshot = service.start("No module named pandas")
    before = snapshot["state"]["probabilities"]
    question = snapshot["question"]["name"]
    snapshot = service.answer(snapshot["state"], question, "unknown")
    assert snapshot["state"]["probabilities"] == before
    assert snapshot["state"]["answers"][question] == "unknown"


def test_duplicate_answer_is_rejected(service):
    snapshot = service.start("No module named pandas")
    question = snapshot["question"]["name"]
    snapshot = service.answer(snapshot["state"], question, "no")
    state = DiagnosisState.from_dict(snapshot["state"])
    with pytest.raises(ValueError, match="已经回答"):
        service.engine.answer(state, question, "yes")


def test_plan_has_prerequisite_risk_and_sources(service):
    snapshot = service.complete(service.start("No module named pandas")["state"])
    assert snapshot["plan"]
    assert snapshot["plan_errors"] == []
    assert all(item["check"] and item["risk_level"] and item["sources"] for item in snapshot["plan"])


def test_high_risk_plan_must_be_blocked():
    item = PlanItem("危险原因", 1.0, "检查", "", "操作", "高风险", "high", False, ({"title": "来源"},))
    assert "高风险" in verify_plan([item])[0]


def test_offline_answer_contains_sources_and_safety_notice(service):
    snapshot = service.complete(service.start("Neo4j Connection refused")["state"])
    answer = render_offline(snapshot)
    assert "证据来源" in answer
    assert "不会自动执行" in answer
    assert "Neo4j" in answer


def test_llm_cannot_invent_command(service):
    class UnsafeLLM:
        def chat(self, *args, **kwargs):
            return "请直接执行 `sudo rm -rf /`。"

    snapshot = service.complete(service.start("Neo4j Connection refused")["state"])
    answer = render_with_llm(snapshot, UnsafeLLM())
    assert "sudo rm" not in answer
    assert "不会自动执行" in answer


def test_neo4j_clear_is_project_scoped():
    from src.graph.builder import GraphBuilder

    class FakeClient:
        def __init__(self):
            self.queries = []

        def run(self, query, parameters=None):
            self.queries.append(query)
            return []

    client = FakeClient()
    GraphBuilder(Settings(), client).clear_all()
    assert "project: 'DebugPath'" in client.queries[0]
    assert "MATCH (n)" not in client.queries[0]


def test_all_frozen_evaluation_cases(service):
    from scripts.evaluate_diagnosis import run_case

    cases = json.loads((ROOT / "data/evaluation/diagnosis_cases.json").read_text(encoding="utf-8"))
    results = [run_case(service, case) for case in cases]
    assert all(item["passed"] for item in results), results


def test_comparison_evaluation_is_reproducible():
    from scripts.evaluate_diagnosis import evaluate

    cases = json.loads((ROOT / "data/evaluation/diagnosis_cases.json").read_text(encoding="utf-8"))
    first = evaluate(cases, random_runs=5, seed=2026)
    second = evaluate(cases, random_runs=5, seed=2026)
    assert first == second
    assert [item["strategy"] for item in first["metrics"]] == [
        "direct",
        "fixed_order",
        "random_question",
        "information_gain",
    ]
    assert first["metrics"][-1]["top1"] == 1.0
