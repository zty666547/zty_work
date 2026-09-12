"""第二版逐阶段子图：记录每一步实际使用的节点和关系。"""
from __future__ import annotations


def stage_subgraph(stage: dict, graph, previous: dict | None = None) -> dict:
    nodes = {
        item["name"]: {"type": entity_type, "props": item.get("props", {})}
        for entity_type, items in graph.entities.items()
        for item in items
    }
    probabilities = {
        item["name"]: item["probability"] for item in stage["candidates"]
    }
    previous_probabilities = {
        item["name"]: item["probability"]
        for item in (previous or stage)["candidates"]
    }
    selected = {stage["issue_name"], *probabilities}
    roles: dict[str, str] = {stage["issue_name"]: "issue"}
    roles.update({name: "candidate_cause" for name in probabilities})

    routing = stage.get("routing") or {}
    routing_candidates = routing.get("candidates") or []
    if routing_candidates:
        for evidence in routing_candidates[0].get("evidence", []):
            selected.add(evidence["name"])
            roles[evidence["name"]] = "routing_evidence"

    question = stage.get("question") or stage.get("next_question")
    if question:
        selected.add(question["name"])
        roles[question["name"]] = "current_question"
    observation = stage.get("observation")
    if observation:
        selected.add(observation)
        roles[observation] = "user_observation"

    context = stage.get("service_context")
    if context:
        selected.add(context)
        roles[context] = "deployment_context"
        context_relations = {
            "CONTEXT_INVOLVES_CLIENT",
            "CLIENT_CONNECTS_TO",
            "SERVICE_EXPOSES",
            "ENDPOINT_REACHABLE_FROM",
        }
        for _ in range(3):
            selected.update(
                relation["target"]
                for relation in graph.relations
                if relation["source"] in selected
                and relation["type"] in context_relations
            )
        for name in selected:
            if nodes.get(name, {}).get("type") in {
                "Service",
                "Endpoint",
                "DeploymentContext",
            }:
                roles.setdefault(name, "service_context")

    if stage["status"] == "completed":
        top = stage["candidates"][0]["name"]
        roles[top] = "final_cause"
        completion_relations = {
            "CAUSE_CONTEXTUALIZED_BY",
            "CONTEXT_CHECKED_BY",
            "CONTEXT_RESOLVED_BY",
            "CHECK_TARGETS_ENDPOINT",
            "REPAIR_CONFIGURES_ENDPOINT",
            "REPAIR_REQUIRES",
            "REPAIR_HAS_RISK",
            "CAUSE_SUPPORTED_BY",
            "CHECK_SUPPORTED_BY",
            "REPAIR_SUPPORTED_BY",
        }
        frontier = {top, *({context} if context else set())}
        for _ in range(3):
            discovered = {
                relation["target"]
                for relation in graph.relations
                if relation["source"] in frontier
                and relation["type"] in completion_relations
            }
            selected.update(discovered)
            frontier = discovered
        for name in selected:
            entity_type = nodes.get(name, {}).get("type")
            if entity_type == "DiagnosticCheck":
                roles.setdefault(name, "final_check")
            elif entity_type == "RepairAction":
                roles.setdefault(name, "final_repair")
            elif entity_type == "Risk":
                roles.setdefault(name, "final_risk")
            elif entity_type == "DocumentSource":
                roles.setdefault(name, "final_source")

    subgraph_nodes = []
    for name in sorted(selected):
        if name not in nodes:
            continue
        probability = probabilities.get(name)
        before = previous_probabilities.get(name, probability)
        subgraph_nodes.append(
            {
                "name": name,
                "type": nodes[name]["type"],
                "role": roles.get(name, "context"),
                "probability": probability,
                "probability_change": (
                    probability - before
                    if probability is not None and before is not None
                    else None
                ),
            }
        )
    subgraph_edges = [
        {
            "source": relation["source"],
            "target": relation["target"],
            "type": relation["type"],
            "props": relation.get("props", {}),
        }
        for relation in graph.relations
        if relation["source"] in selected and relation["target"] in selected
    ]
    return {
        "step": stage["step"],
        "event": stage["event"],
        "status": stage["status"],
        "stop_reason": stage["stop_reason"],
        "nodes": subgraph_nodes,
        "edges": subgraph_edges,
    }
