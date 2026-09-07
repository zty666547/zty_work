import json
from copy import deepcopy

import pytest
from streamlit.testing.v1 import AppTest

from src.diagnosis.models import DiagnosisState
from src.diagnosis.service import DiagnosisService
from src.diagnosis.trajectory import stage_dot


def test_rounds_are_independent_and_unknown_does_not_change_probabilities():
    service = DiagnosisService()
    first = service.start("torch.cuda.is_available() 返回 False")
    saved = deepcopy(first)
    second = service.answer(first["state"], first["question"]["name"], "unknown")
    assert first == saved
    trace = second["state"]["trajectory"]
    assert len(trace) == 2
    assert trace[0]["candidates"] == trace[1]["candidates"]
    assert trace[1]["answer"] == "unknown"
    restored = DiagnosisState.from_dict(json.loads(json.dumps(second["state"])))
    assert service.snapshot(restored)["state"]["trajectory"] == trace
    assert len(restored.trajectory) == 2


def test_stop_is_recorded_once_and_rejects_further_answers():
    service = DiagnosisService()
    first = service.start("ModuleNotFoundError")
    final = service.complete(first["state"])
    assert final["state"]["trajectory"][-1]["stop_reason"] == "用户主动结束追问"
    assert len(service.complete(final["state"])["state"]["trajectory"]) == 2
    with pytest.raises(ValueError, match="已经结束"):
        service.answer(final["state"], first["question"]["name"], "yes")


def test_full_trace_preserves_candidates_and_explains_stop():
    service = DiagnosisService()
    snapshot = service.start("Neo4j Connection refused")
    while snapshot["question"]:
        snapshot = service.answer(snapshot["state"], snapshot["question"]["name"], "yes")
    stages = snapshot["state"]["trajectory"]
    assert len(stages) == len(snapshot["state"]["asked_questions"]) + 1
    for stage in stages:
        assert sum(c["probability"] for c in stage["candidates"]) == pytest.approx(1)
        assert len(stage["candidates"]) == len(stages[0]["candidates"])
    assert stages[-1]["stop_reason"]
    dot = stage_dot(stages[-1], service.graph, stages[-2])
    assert "当前首位" in dot and "来源" in dot and "前置检查" in dot


def test_web_replay_does_not_rewind_live_diagnosis():
    app = AppTest.from_file("app.py", default_timeout=20).run()
    app.text_area[0].set_value("ModuleNotFoundError").run()
    next(b for b in app.button if b.label == "开始诊断").click().run()
    assert not app.exception
    next(b for b in app.button if b.label == "提交观察结果").click().run()
    assert not app.exception
    state = deepcopy(app.session_state["diagnosis"]["state"])
    app.select_slider[0].set_value(0).run()
    assert not app.exception
    assert app.session_state["diagnosis"]["state"] == state
    next(b for b in app.button if b.label == "结束追问，查看当前方案").click().run()
    assert not app.exception
    assert app.session_state["diagnosis"]["state"]["stop_reason"] == "用户主动结束追问"
