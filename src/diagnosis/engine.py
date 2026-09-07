"""基于因果图和信息增益的确定性主动诊断引擎。"""
from __future__ import annotations

import math
from collections import defaultdict

from config.settings import Settings
from src.data.loader import StructuredGraph
from src.diagnosis.models import DiagnosisState, QuestionChoice


class UnknownIssueError(ValueError):
    """输入未命中当前三个诊断场景。"""


class DiagnosisEngine:
    def __init__(self, graph: StructuredGraph, settings: Settings | None = None):
        self.graph = graph
        self.settings = settings or Settings()
        self.nodes: dict[str, dict] = {}
        self.types: dict[str, str] = {}
        for entity_type, items in graph.entities.items():
            for item in items:
                self.nodes[item["name"]] = dict(item.get("props") or {})
                self.types[item["name"]] = entity_type

        self.by_relation: dict[str, list[dict]] = defaultdict(list)
        for relation in graph.relations:
            self.by_relation[relation["type"]].append(relation)

        self.issue_causes = self._targets_by_source("HAS_POSSIBLE_CAUSE")
        self.issue_questions = self._targets_by_source("HAS_QUESTION")
        self.question_observation = {
            row["source"]: row["target"] for row in self.by_relation["CHECKS"]
        }
        self.observation_effects = self._effects_by_observation()

    def _targets_by_source(self, relation_type: str) -> dict[str, list[dict]]:
        result: dict[str, list[dict]] = defaultdict(list)
        for row in self.by_relation[relation_type]:
            result[row["source"]].append(
                {"name": row["target"], **dict(row.get("props") or {})}
            )
        return result

    def _effects_by_observation(self) -> dict[str, dict[str, float]]:
        result: dict[str, dict[str, float]] = defaultdict(dict)
        for row in self.by_relation["OBSERVATION_SUPPORTS"]:
            likelihood = float((row.get("props") or {}).get("p_yes_given_cause", 0.5))
            result[row["source"]][row["target"]] = min(max(likelihood, 0.01), 0.99)
        return result

    def supported_issues(self) -> list[dict]:
        return [
            {"name": name, **self.nodes[name]}
            for name, entity_type in self.types.items()
            if entity_type == "Issue"
        ]

    def identify_issue(self, report: str) -> str:
        normalized = report.casefold()
        scored: list[tuple[int, str]] = []
        for issue in self.supported_issues():
            terms = [issue["name"], *(issue.get("aliases") or [])]
            if issue.get("example"):
                terms.append(issue["example"])
            score = sum(len(term) for term in terms if term.casefold() in normalized)
            if score:
                scored.append((score, issue["name"]))
        if not scored:
            examples = "；".join(item.get("example", item["name"]) for item in self.supported_issues())
            raise UnknownIssueError(f"当前未识别该故障。可尝试：{examples}")
        return max(scored, key=lambda item: (item[0], item[1]))[1]

    def start(self, report: str) -> DiagnosisState:
        report = report.strip()
        if not report:
            raise ValueError("故障描述不能为空")
        issue_name = self.identify_issue(report)
        causes = self.issue_causes[issue_name]
        probabilities = {
            item["name"]: float(item.get("prior", 1.0)) for item in causes
        }
        self._normalize(probabilities)
        return DiagnosisState(
            report=report,
            issue_name=issue_name,
            probabilities=probabilities,
        )

    @staticmethod
    def _normalize(probabilities: dict[str, float]) -> None:
        total = sum(max(value, 0.0) for value in probabilities.values())
        if total <= 0:
            uniform = 1 / max(len(probabilities), 1)
            probabilities.update({name: uniform for name in probabilities})
            return
        probabilities.update(
            {name: max(value, 0.0) / total for name, value in probabilities.items()}
        )

    @staticmethod
    def _entropy(probabilities: dict[str, float]) -> float:
        return -sum(p * math.log2(p) for p in probabilities.values() if p > 0)

    def entropy(self, state: DiagnosisState) -> float:
        """返回当前候选原因分布的香农熵，供评估与界面解释使用。"""
        return self._entropy(state.probabilities)

    def _question_gain(self, state: DiagnosisState, question: str) -> tuple[float, float]:
        observation = self.question_observation[question]
        effects = self.observation_effects[observation]
        p_yes = sum(
            probability * effects.get(cause, 0.5)
            for cause, probability in state.probabilities.items()
        )
        p_yes = min(max(p_yes, 1e-9), 1 - 1e-9)
        yes_posterior = {
            cause: probability * effects.get(cause, 0.5) / p_yes
            for cause, probability in state.probabilities.items()
        }
        no_posterior = {
            cause: probability * (1 - effects.get(cause, 0.5)) / (1 - p_yes)
            for cause, probability in state.probabilities.items()
        }
        expected = p_yes * self._entropy(yes_posterior) + (1 - p_yes) * self._entropy(no_posterior)
        gain = max(0.0, self._entropy(state.probabilities) - expected)
        return gain, p_yes

    def available_questions(self, state: DiagnosisState) -> list[QuestionChoice]:
        """列出尚未回答的问题及其当前信息增益，不改变诊断状态。"""
        choices: list[QuestionChoice] = []
        for item in self.issue_questions[state.issue_name]:
            question = item["name"]
            if question in state.asked_questions:
                continue
            gain, p_yes = self._question_gain(state, question)
            props = self.nodes[question]
            cost = float(props.get("cost", 1.0))
            risk_cost = float(props.get("risk_cost", 0.0))
            utility = gain - 0.02 * cost - 0.05 * risk_cost
            choices.append(
                QuestionChoice(
                    name=question,
                    text=props["text"],
                    yes_label=props.get("yes_label", "是"),
                    no_label=props.get("no_label", "否"),
                    information_gain=gain,
                    utility=utility,
                    reason=f"预计可减少 {gain:.3f} bit 不确定性；当前回答“是”的预测概率为 {p_yes:.0%}",
                )
            )
        return choices

    def next_question(self, state: DiagnosisState) -> QuestionChoice | None:
        if state.status != "questioning":
            return None
        choices = self.available_questions(state)
        if not choices:
            state.status = "completed"
            state.stop_reason = "没有剩余问题"
            return None
        best = max(choices, key=lambda item: (item.utility, item.information_gain, item.name))
        if best.information_gain < self.settings.min_information_gain:
            state.status = "completed"
            state.stop_reason = "剩余问题的信息增益不足"
            return None
        return best

    def answer(self, state: DiagnosisState, question_name: str, answer: str) -> DiagnosisState:
        if state.status != "questioning":
            raise ValueError("诊断已经结束，请重新开始")
        if question_name in state.asked_questions:
            raise ValueError("该问题已经回答过")
        if question_name not in {item["name"] for item in self.issue_questions[state.issue_name]}:
            raise ValueError("问题不属于当前诊断场景")
        if answer not in {"yes", "no", "unknown"}:
            raise ValueError("answer 必须是 yes、no 或 unknown")

        state.asked_questions.append(question_name)
        state.answers[question_name] = answer
        if answer != "unknown":
            observation = self.question_observation[question_name]
            effects = self.observation_effects[observation]
            for cause, probability in list(state.probabilities.items()):
                p_yes = effects.get(cause, 0.5)
                likelihood = p_yes if answer == "yes" else 1 - p_yes
                state.probabilities[cause] = probability * likelihood
            self._normalize(state.probabilities)

        top_probability = max(state.probabilities.values(), default=0.0)
        if len(state.asked_questions) >= self.settings.max_questions:
            state.status = "completed"
            state.stop_reason = "达到最大追问轮数"
        elif len(state.asked_questions) >= 2 and top_probability >= self.settings.confidence_threshold:
            state.status = "completed"
            state.stop_reason = "最高候选概率达到停止阈值"
        elif self.next_question(state) is None:
            state.status = "completed"
        return state

    def ranked_candidates(self, state: DiagnosisState) -> list[dict]:
        return [
            {
                "name": cause,
                "probability": probability,
                "description": self.nodes[cause].get("description", ""),
            }
            for cause, probability in sorted(
                state.probabilities.items(), key=lambda item: (-item[1], item[0])
            )
        ]
