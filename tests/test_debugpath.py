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
    assert sum(map(len, service.graph.entities.values())) == 132
    assert len(service.graph.relations) == 345


def test_processed_graph_artifact_is_deterministic():
    from src.graph.artifact import create_graph_artifact

    graph = load_knowledge_base(KNOWLEDGE, EVIDENCE)
    first = create_graph_artifact(graph, ["knowledge", "evidence"])
    second = create_graph_artifact(graph, ["evidence", "knowledge"])
    assert first == second
    assert first["stats"]["nodes"] == 132
    assert first["stats"]["relationships"] == 345
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
        (
            "module 'code' has no attribute 'InteractiveConsole' (consider renaming code.py)",
            "Python模块无法导入",
        ),
        ("torch.cuda.is_available() False", "PyTorch无法使用GPU"),
        ("torch.cuda.is_available()返回False", "PyTorch无法使用GPU"),
        ("Torch not compiled with CUDA enabled", "PyTorch无法使用GPU"),
        ("The detected CUDA version 12.1 mismatches the version", "PyTorch无法使用GPU"),
        ("Failed to initialize NVML: Driver Not Loaded", "PyTorch无法使用GPU"),
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


def test_real_case_split_is_complete_and_leak_free():
    from scripts.audit_real_case_split import build_report

    report = build_report()
    assert report["development_cases"] == 28
    assert report["frozen_test_cases"] == 14
    assert report["unconfirmed_cases"] == 3
    assert report["development_causes"] == 14
    assert report["development_min_per_cause"] == 2
    assert report["frozen_test_causes"] == 14
    assert report["frozen_test_min_per_cause"] == 1
    assert report["source_overlap"] == []
    assert report["test_ready"] is True


def test_frozen_test_seal_matches_current_cases():
    from scripts.seal_frozen_test import build_seal

    saved = json.loads(
        (ROOT / "data/evaluation/frozen_test_seal.json").read_text(encoding="utf-8")
    )
    assert build_seal() == saved
    assert saved["case_count"] == 14
    assert saved["cause_count"] == 14


def test_frozen_test_evaluation_preflight_does_not_run_cases():
    from scripts.evaluate_frozen_test import prepare_evaluation

    cases, model, seal, protocol = prepare_evaluation()
    assert len(cases) == 14
    assert len({case["expected_top_cause"] for case in cases}) == 14
    assert model["frozen"] is True
    assert seal["case_ids"] == [case["id"] for case in cases]
    assert [item["id"] for item in protocol["protocol"]["strategies"]] == [
        "direct_no_question",
        "fixed_order",
        "random_question",
        "pure_information_gain",
        "full_answerability_aware",
    ]
    assert protocol["protocol"]["random"] == {"runs": 100, "seed": 2026}


def test_pure_information_gain_policy_uses_raw_gain_only(service):
    from src.diagnosis.policies import PureInformationGainPolicy

    snapshot = service.start("APIConnectionError: Connection refused")
    state = DiagnosisState.from_dict(snapshot["state"])
    choices = service.engine.available_questions(state, answerability_aware=False)
    expected = max(choices, key=lambda item: (item.information_gain, item.name))
    actual = PureInformationGainPolicy().choose(service.engine, state)
    assert actual is not None
    assert actual.name == expected.name


def test_frozen_evaluator_counts_unrecognized_report_as_end_to_end_failure(service):
    from scripts.evaluate_frozen_test import run_strategy_case
    from src.diagnosis.policies import DirectPolicy

    row = run_strategy_case(
        service,
        {
            "id": "unrecognized_case",
            "family": "dependency",
            "report": "这是一条当前系统无法归类的全新故障描述",
            "expected_top_cause": "依赖包未安装",
            "answers": {},
        },
        DirectPolicy(),
    )
    assert row["passed"] is False
    assert row["rank"] is None
    assert row["questions"] == 0
    assert row["stop_reason"] == "故障族识别失败"
    assert row["entry_error"]


def test_v2_issue_router_uses_graph_evidence_when_signature_is_missing(service):
    from src.retrieval.issue_router import IssueRouter

    router = IssueRouter(service.graph)
    examples = {
        "项目目录存在同名py文件，import加载的是当前目录文件": "Python模块无法导入",
        "nvidia.ko内核模块没有加载，驱动无法与GPU通信": "PyTorch无法使用GPU",
        "127.0.0.1:1933没有进程监听，需要启动本地服务": "服务或配置连接失败",
    }
    for report, expected in examples.items():
        route = router.route(report)
        assert route is not None
        assert route["issue"] == expected
        assert route["signature_score"] == 0.0
        assert route["evidence_score"] > 0.0
        assert route["evidence"]


def test_v2_issue_router_keeps_signature_and_evidence_explanations(service):
    from src.retrieval.issue_router import IssueRouter

    route = IssueRouter(service.graph).route("ModuleNotFoundError: No module named pandas")
    assert route is not None
    assert route["issue"] == "Python模块无法导入"
    assert "ModuleNotFoundError" in route["matched_signatures"]
    assert route["signature_score"] == 1.0
    assert route["evidence_score"] > 0.0


def test_v2_service_routes_previous_signature_gap_without_changing_v1(service):
    from src.diagnosis.engine import UnknownIssueError
    from src.diagnosis.service_v2 import DiagnosisServiceV2

    report = "项目目录存在同名numpy.py，import后加载了当前目录文件"
    with pytest.raises(UnknownIssueError):
        service.start(report)

    snapshot = DiagnosisServiceV2().start(report)
    assert snapshot["state"]["issue_name"] == "Python模块无法导入"
    assert snapshot["routing"]["status"] == "routed"
    assert snapshot["routing"]["selected_issue"] == "Python模块无法导入"
    assert snapshot["routing"]["candidates"][0]["evidence"]


def test_v2_router_rejects_input_without_retrieval_evidence(service):
    from src.retrieval.issue_router import IssueRouter

    decision = IssueRouter(service.graph).decide("今天天气怎么样")
    assert decision["status"] == "unsupported"
    assert decision["selected_issue"] is None


def test_v2_router_requests_cross_family_clarification(service):
    from src.diagnosis.service_v2 import AmbiguousIssueError, DiagnosisServiceV2
    from src.retrieval.issue_router import IssueRouter

    report = "服务启动后Python模块找不到"
    decision = IssueRouter(service.graph).decide(report)
    assert decision["status"] == "ambiguous"
    assert decision["selected_issue"] is None
    assert "模块无法导入" in decision["clarification"]
    assert "服务/API" in decision["clarification"]
    with pytest.raises(AmbiguousIssueError):
        DiagnosisServiceV2().start(report)


def test_v2_service_context_graph_drives_ollama_specific_plan():
    from src.diagnosis.service_v2 import DiagnosisServiceV2

    service = DiagnosisServiceV2()
    snapshot = service.start(
        "宿主机Ollama可以访问，但Docker中的Open WebUI连接失败"
    )
    assert snapshot["service_context"] == "Open WebUI容器访问宿主机Ollama"
    assert snapshot["question"]["name"] == "Q-宿主机正常但容器访问失败"

    snapshot = service.answer(
        snapshot["state"],
        snapshot["question"]["name"],
        "yes",
    )
    snapshot = service.answer(
        snapshot["state"],
        snapshot["question"]["name"],
        "no",
    )
    assert snapshot["state"]["status"] == "completed"
    assert snapshot["candidates"][0]["name"] == "服务地址配置错误"
    assert snapshot["candidates"][0]["probability"] > 0.90
    assert snapshot["decision"]["sufficient"] is True
    assert "/api/tags" in snapshot["plan"][0]["command"]
    assert "OLLAMA_BASE_URL" in snapshot["plan"][0]["repair"]
    assert snapshot["plan"][0]["risk_level"] == "low"
    assert len(snapshot["plan"][0]["sources"]) == 3
    assert snapshot["plan_errors"] == []


def test_v2_context_question_does_not_leak_into_unrelated_service_cases():
    from src.diagnosis.models import DiagnosisState
    from src.diagnosis.service_v2 import DiagnosisServiceV2

    service = DiagnosisServiceV2()
    snapshot = service.start("uvicorn启动失败，Address already in use，端口被占用")
    state = DiagnosisState.from_dict(snapshot["state"])
    names = {choice.name for choice in service.engine.available_questions(state)}
    assert "Q-宿主机正常但容器访问失败" not in names


def test_v2_demo_subgraph_contains_every_used_node_type():
    from scripts.export_v2_demo import build_demo

    report = build_demo()
    assert report["final"]["cause"] == "服务地址配置错误"
    assert report["final"]["decision"]["sufficient"] is True
    final_types = {node["type"] for node in report["subgraphs"][-1]["nodes"]}
    assert {
        "Issue",
        "Cause",
        "DiagnosticQuestion",
        "Observation",
        "EvidenceChunk",
        "Service",
        "Endpoint",
        "DeploymentContext",
        "DiagnosticCheck",
        "RepairAction",
        "Risk",
        "DocumentSource",
    } <= final_types


def test_v2_graph_artifact_is_deterministic_and_service_aware():
    from scripts.prepare_graph_v2 import prepare

    first = prepare()["artifact"]
    second = prepare()["artifact"]
    assert first["format"] == "debugpath-graph-v2"
    assert first["content_sha256"] == second["content_sha256"]
    assert first["stats"]["nodes"] == 144
    assert first["stats"]["relationships"] == 366
    assert first["stats"]["entity_types"]["Service"] == 2
    assert first["stats"]["entity_types"]["Endpoint"] == 1
    assert first["stats"]["entity_types"]["DeploymentContext"] == 1


def test_v2_strategy_development_comparison_is_scoped_and_reproducible():
    from scripts.evaluate_v2_strategy import evaluate

    report = evaluate()
    assert "不是第二版无偏测试成绩" in report["warning"]
    assert len(report["summaries"]) == 4
    assert report["initial_question_difference_count"] > 0
    by_key = {
        (item["cohort"], item["strategy"]): item
        for item in report["summaries"]
    }
    assert by_key[("original_development", "answerability_aware")]["top1"] == 1.0
    assert (
        by_key[("original_development", "answerability_aware")]["top1"]
        >= by_key[("original_development", "pure_information_gain")]["top1"]
    )


def test_calibration_ablation_is_reproducible_and_scoped_to_development():
    from scripts.evaluate_calibration import evaluate

    first = evaluate()
    second = evaluate()
    assert first == second
    assert first["case_count"] == 28
    metrics = {item["algorithm"]: item for item in first["metrics"]}
    assert metrics["combined"]["top1"] >= metrics["before_calibration"]["top1"]
    assert metrics["combined"]["wrong_confident_stop_rate"] == 0.0


def test_stage2_model_freeze_matches_current_graph_and_settings():
    from scripts.audit_model_freeze import build_report

    report = build_report()
    assert report["frozen"] is True
    assert report["graph_matches"] is True
    assert report["settings_checked"] == 12
    assert report["implementation_files_checked"] == 6
    assert all(report["implementation_matches"].values())
    assert report["test_protocol"]["minimum_cases"] == 14


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
    assert (
        report["summary"]["causes_with_confirmed_case"]
        == report["target"]["total_causes"]
    )
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


def test_service_config_public_error_aliases_are_identified(service):
    samples = [
        "APIConnectionError: Connection error while calling local model",
        "AuthenticationError: Incorrect API key provided",
        "Error: No API key provided",
    ]
    for report in samples:
        match = service.engine.identify_issue(report)
        assert match == "服务或配置连接失败", (report, match)


def test_host_local_health_observation_separates_wrong_address_from_stopped_service(service):
    snapshot = service.start("APIConnectionError: Connection refused")
    snapshot = service.answer(snapshot["state"], "Q-是否连接被拒绝", "yes")
    snapshot = service.answer(
        snapshot["state"], "Q-目标主机本机检查是否成功", "yes"
    )
    probabilities = {
        item["name"]: item["probability"] for item in snapshot["candidates"]
    }
    assert probabilities["服务地址配置错误"] > probabilities["目标服务未启动"]


def test_hybrid_ablation_improves_initial_ranking():
    from scripts.evaluate_ablation import evaluate_ablation
    from scripts.evaluate_diagnosis import load_cases

    report = evaluate_ablation(load_cases())
    metrics = {item["strategy"]: item for item in report["metrics"]}
    assert metrics["hybrid_no_question"]["top1"] > metrics["graph_prior_only"]["top1"]
    assert metrics["hybrid_active"]["top1"] == 1.0
    assert metrics["hybrid_active"]["avg_questions"] < metrics["graph_active"]["avg_questions"]
