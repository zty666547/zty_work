"""DebugPath核心测试：不连接Neo4j，不调用大模型。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.settings import Settings
from src.data.loader import load_knowledge_base, load_structured
from src.diagnosis.engine import DiagnosisEngine, UnknownIssueError
from src.diagnosis.case_export import build_case_export, sanitize_text
from src.diagnosis.generator import render_offline, render_with_llm
from src.diagnosis.models import DiagnosisState, PlanItem
from src.diagnosis.planner import PlanBuilder, verify_plan
from src.diagnosis.service import DiagnosisService

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE = ROOT / "data/raw/debugpath_knowledge.json"
EVIDENCE = ROOT / "data/raw/debugpath_evidence.json"


@pytest.fixture(scope="module")
def service() -> DiagnosisService:
    return DiagnosisService(Settings())


def test_knowledge_graph_is_valid_and_substantial():
    graph = load_structured(KNOWLEDGE)
    assert sum(map(len, graph.entities.values())) >= 90
    assert len(graph.relations) >= 200
    assert len(graph.entities["Issue"]) == 3
    assert len(graph.entities["DocumentSource"]) >= 8


def test_evidence_layer_is_merged_into_runtime_graph(service):
    assert len(service.graph.entities["EvidenceChunk"]) == 30
    assert sum(map(len, service.graph.entities.values())) == 130
    assert len(service.graph.relations) == 338


def test_processed_graph_artifact_is_deterministic():
    from src.graph.artifact import create_graph_artifact

    graph = load_knowledge_base(KNOWLEDGE, EVIDENCE)
    first = create_graph_artifact(graph, ["knowledge", "evidence"])
    second = create_graph_artifact(graph, ["evidence", "knowledge"])
    assert first == second
    assert first["stats"]["nodes"] == 130
    assert first["stats"]["relationships"] == 338
    assert len(first["content_sha256"]) == 64


def test_neo4j_read_only_inspection_matches_artifact():
    from scripts.check_neo4j import inspect_remote
    from src.graph.artifact import create_graph_artifact

    expected = create_graph_artifact(
        load_knowledge_base(KNOWLEDGE, EVIDENCE)
    )["stats"]

    class FakeClient:
        def run(self, query, parameters=None):
            if "RETURN count(n) AS count" in query:
                return [{"count": expected["nodes"]}]
            if "RETURN count(r) AS count" in query:
                return [{"count": expected["relationships"]}]
            if "RETURN entity_type" in query:
                return [
                    {"entity_type": name, "count": count}
                    for name, count in expected["entity_types"].items()
                ]
            if "RETURN type(r) AS relation_type" in query:
                return [
                    {"relation_type": name, "count": count}
                    for name, count in expected["relation_types"].items()
                ]
            raise AssertionError(f"意外查询：{query}")

    assert inspect_remote(FakeClient()) == expected


def test_bm25_evidence_changes_initial_ranking(service):
    snapshot = service.start("macOS Apple Silicon上CUDA不可用")
    assert snapshot["state"]["evidence"][0]["chunk_id"] == "E017"
    assert snapshot["candidates"][0]["name"] == "当前平台不提供CUDA"


def test_evidence_survives_question_round_trip(service):
    snapshot = service.start("Neo4j Connection refused localhost:7687")
    evidence = snapshot["state"]["evidence"]
    snapshot = service.answer(snapshot["state"], snapshot["question"]["name"], "yes")
    assert snapshot["state"]["evidence"] == evidence


@pytest.mark.parametrize(
    ("report", "issue"),
    [
        ("ModuleNotFoundError: No module named x", "Python模块无法导入"),
        ("torch.cuda.is_available() False", "PyTorch无法使用GPU"),
        ("torch.cuda.is_available()返回False", "PyTorch无法使用GPU"),
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
    assert snapshot["question"]["expected_information_gain"] > 0
    assert 0 < snapshot["question"]["answerability"] <= 1
    assert "不确定性" in snapshot["question"]["reason"]
    assert "可回答率" in snapshot["question"]["reason"]


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


def test_unknown_answers_do_not_satisfy_robust_confidence_stop(service):
    snapshot = service.start("No module named pandas")
    snapshot["state"]["probabilities"] = {
        name: (0.9 if index == 0 else 0.1 / (len(snapshot["candidates"]) - 1))
        for index, name in enumerate(item["name"] for item in snapshot["candidates"])
    }
    for _ in range(2):
        assert snapshot["question"] is not None
        snapshot = service.answer(
            snapshot["state"], snapshot["question"]["name"], "unknown"
        )
    assert snapshot["state"]["status"] == "questioning"
    assert not snapshot["decision"]["sufficient"]


def test_max_questions_with_weak_evidence_abstains(service):
    snapshot = service.start("No module named pandas")
    while snapshot["state"]["status"] == "questioning":
        snapshot = service.answer(
            snapshot["state"], snapshot["question"]["name"], "unknown"
        )
    assert not snapshot["decision"]["sufficient"]
    assert "证据不足" in snapshot["state"]["stop_reason"]


def test_answerability_reduces_effective_information_gain(service):
    snapshot = service.start("No module named pandas")
    state = DiagnosisState.from_dict(snapshot["state"])
    for question in service.engine.available_questions(state):
        assert question.expected_information_gain == pytest.approx(
            question.information_gain * question.answerability
        )


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


def test_llm_can_only_reorder_verified_claims(service):
    class ValidPlannerLLM:
        def chat_json(self, *args, **kwargs):
            return {
                "claim_order": ["C2", "C1", "C3"],
                "evidence_ids": ["E024"],
                "emphasis": "safety",
            }

    snapshot = service.complete(service.start("Neo4j Connection refused")['state'])
    answer = render_with_llm(snapshot, ValidPlannerLLM())
    assert answer.index("[C2]") < answer.index("[C1]") < answer.index("[C3]")
    assert "优先保留前置检查" in answer
    assert "E024" in answer


def test_llm_unknown_claim_or_evidence_falls_back(service):
    class InventingPlannerLLM:
        def chat_json(self, *args, **kwargs):
            return {
                "claim_order": ["C999"],
                "evidence_ids": ["E999"],
                "emphasis": "diagnosis",
            }

    snapshot = service.complete(service.start("Neo4j Connection refused")["state"])
    assert render_with_llm(snapshot, InventingPlannerLLM()) == render_offline(snapshot)

    class MalformedPlannerLLM:
        def chat_json(self, *args, **kwargs):
            return {
                "claim_order": [{"invented": True}],
                "evidence_ids": [{"invented": True}],
                "emphasis": "diagnosis",
            }

    assert render_with_llm(snapshot, MalformedPlannerLLM()) == render_offline(snapshot)


def test_injection_guard_evaluation_rejects_all_invalid_cases():
    from scripts.evaluate_injection import evaluate

    report = evaluate()
    assert report["valid_cases"] == 9
    assert report["invalid_cases"] == 24
    assert report["valid_acceptance_rate"] == 1.0
    assert report["invalid_rejection_rate"] == 1.0


def test_answerability_aware_evaluation_is_reproducible():
    from scripts.evaluate_active_algorithm import evaluate
    from scripts.evaluate_diagnosis import load_cases

    first = evaluate(load_cases())
    second = evaluate(load_cases())
    assert first == second
    assert [row["algorithm"] for row in first["metrics"]] == [
        "legacy_information_gain",
        "answerability_aware",
    ]


def test_public_cases_exclude_unconfirmed_roots_from_accuracy():
    from scripts.evaluate_public_cases import evaluate, load_public_cases

    confirmed, pending = load_public_cases()
    report = evaluate()
    assert confirmed and pending
    assert report["confirmed_cases"] == len(confirmed)
    assert report["unconfirmed_cases"] == len(pending)
    assert all(case["root_cause_status"] == "confirmed" for case in confirmed)


def test_second_stage_gap_audit_covers_every_cause():
    from scripts.audit_second_stage import build_report
    from scripts.evaluate_public_cases import load_public_cases

    report = build_report()
    confirmed, _ = load_public_cases()
    confirmed_causes = {case["expected_top_cause"] for case in confirmed}
    assert report["target"]["total_causes"] == 14
    assert len({row["cause"] for row in report["causes"]}) == 14
    assert report["summary"]["confirmed_cases"] == len(confirmed)
    assert report["summary"]["causes_with_confirmed_case"] == len(confirmed_causes)
    assert all(
        row["graph"][field] > 0
        for row in report["causes"]
        for field in ("observations", "checks", "repairs", "direct_sources")
    )


def test_case_export_redacts_private_environment_data(service):
    snapshot = service.complete(
        service.start(
            "sk-abcdefghijklmnop 在 /Users/alice/project 报错，"
            "联系 alice@example.com，远端为 192.168.1.8，localhost为127.0.0.1；"
            "ModuleNotFoundError"
        )["state"]
    )
    exported = build_case_export(
        snapshot,
        actual_cause=snapshot["candidates"][0]["name"],
        confirmed=True,
        note=r"Bearer abcdefghijklmnop，日志在 C:\Users\alice\work",
    )
    encoded = json.dumps(exported, ensure_ascii=False)
    assert "sk-abcdefghijklmnop" not in encoded
    assert "alice@example.com" not in encoded
    assert "192.168.1.8" not in encoded
    assert "/Users/alice" not in encoded
    assert r"C:\Users\alice" not in encoded
    assert "127.0.0.1" in encoded
    assert exported["include_in_accuracy"]


def test_unconfirmed_case_export_cannot_enter_accuracy(service):
    snapshot = service.complete(service.start("Neo4j Connection refused")["state"])
    exported = build_case_export(snapshot, actual_cause=None, confirmed=True)
    assert exported["root_cause_status"] == "unconfirmed"
    assert not exported["include_in_accuracy"]
    assert exported["actual_cause"] is None


def test_sanitize_text_preserves_non_sensitive_diagnostic_terms():
    assert sanitize_text("Neo4j localhost:7687 ModuleNotFoundError") == (
        "Neo4j localhost:7687 ModuleNotFoundError"
    )


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


def test_neo4j_build_rejects_incomplete_write():
    from src.graph.builder import GraphBuilder

    class EmptyClient:
        def run(self, query, parameters=None):
            if "RETURN count(n) AS c" in query or "RETURN count(r) AS c" in query:
                return [{"c": 0}]
            return []

    with pytest.raises(RuntimeError, match="写入后规模不一致"):
        GraphBuilder(Settings(), EmptyClient()).build(
            [{"name": "测试故障", "type": "Issue", "props": {}}],
            [],
        )


def test_all_frozen_evaluation_cases(service):
    from scripts.evaluate_diagnosis import load_cases, run_case

    cases = load_cases()
    results = [run_case(service, case) for case in cases]
    assert all(item["passed"] for item in results), results


def test_comparison_evaluation_is_reproducible():
    from scripts.evaluate_diagnosis import evaluate, load_cases

    cases = load_cases()
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


def test_benchmark_is_balanced_and_source_traceable(service):
    from scripts.evaluate_diagnosis import load_cases

    cases = load_cases()
    assert len(cases) == 30
    assert {item["family"] for item in cases} == {
        "python_import",
        "pytorch_gpu",
        "service_config",
    }
    assert all(sum(item["family"] == family for item in cases) == 10 for family in {
        "python_import", "pytorch_gpu", "service_config"
    })
    assert sum(item["split"] == "dev" for item in cases) == 9
    assert sum(item["split"] == "test" for item in cases) == 21
    assert all(item["source_refs"] for item in cases)
    expected_causes = {
        cause["name"]
        for causes in service.engine.issue_causes.values()
        for cause in causes
    }
    assert {item["expected_top_cause"] for item in cases} == expected_causes


def test_hybrid_ablation_improves_initial_ranking():
    from scripts.evaluate_ablation import evaluate_ablation
    from scripts.evaluate_diagnosis import load_cases

    report = evaluate_ablation(load_cases())
    metrics = {item["strategy"]: item for item in report["metrics"]}
    assert metrics["hybrid_no_question"]["top1"] > metrics["graph_prior_only"]["top1"]
    assert metrics["hybrid_active"]["top1"] == 1.0
    assert metrics["hybrid_active"]["avg_questions"] < metrics["graph_active"]["avg_questions"]
