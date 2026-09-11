#!/usr/bin/env python3
"""检查真实案例的开发/冻结测试边界和来源独立性。"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = ROOT / "data/evaluation/public_cases.json"
SPLIT_PATH = ROOT / "data/evaluation/real_case_split.json"


def build_report() -> dict:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    split = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
    by_id = {case["id"]: case for case in cases}
    if len(by_id) != len(cases):
        raise ValueError("案例ID重复")

    groups = {
        "development": split["development_ids"],
        "frozen_test": split["frozen_test_ids"],
        "unconfirmed": split["unconfirmed_ids"],
    }
    listed = [case_id for ids in groups.values() for case_id in ids]
    if len(listed) != len(set(listed)):
        raise ValueError("同一案例被分配到多个数据集")
    if set(listed) != set(by_id):
        missing = sorted(set(by_id) - set(listed))
        unknown = sorted(set(listed) - set(by_id))
        raise ValueError(f"划分未覆盖全部案例：missing={missing}, unknown={unknown}")

    for case_id in groups["development"] + groups["frozen_test"]:
        if by_id[case_id]["root_cause_status"] != "confirmed":
            raise ValueError(f"未确认案例不能进入实验集：{case_id}")
    for case_id in groups["unconfirmed"]:
        if by_id[case_id]["root_cause_status"] != "unconfirmed":
            raise ValueError(f"确认案例不应进入未确认集：{case_id}")

    dev_sources = {by_id[case_id]["source_url"] for case_id in groups["development"]}
    test_sources = {by_id[case_id]["source_url"] for case_id in groups["frozen_test"]}
    overlap = sorted(dev_sources & test_sources)
    if overlap:
        raise ValueError(f"开发集与测试集来源重复：{overlap}")

    cause_counts = Counter(
        by_id[case_id]["expected_top_cause"] for case_id in groups["development"]
    )
    return {
        "development_cases": len(groups["development"]),
        "frozen_test_cases": len(groups["frozen_test"]),
        "unconfirmed_cases": len(groups["unconfirmed"]),
        "development_causes": len(cause_counts),
        "development_min_per_cause": min(cause_counts.values(), default=0),
        "source_overlap": overlap,
        "test_ready": bool(groups["frozen_test"]),
    }


def main() -> None:
    report = build_report()
    print(
        f"开发集：{report['development_cases']}；"
        f"冻结测试集：{report['frozen_test_cases']}；"
        f"未确认集：{report['unconfirmed_cases']}"
    )
    print(
        f"开发集覆盖：{report['development_causes']}类原因，"
        f"每类至少{report['development_min_per_cause']}条"
    )
    print("测试集状态：" + ("可运行" if report["test_ready"] else "尚未收集，禁止报告最终性能"))


if __name__ == "__main__":
    main()
