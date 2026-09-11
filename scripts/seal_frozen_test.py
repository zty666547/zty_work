#!/usr/bin/env python3
"""为冻结测试集生成或核对确定性内容指纹。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from audit_real_case_split import build_report

ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = ROOT / "data/evaluation/public_cases.json"
SPLIT_PATH = ROOT / "data/evaluation/real_case_split.json"
SEAL_PATH = ROOT / "data/evaluation/frozen_test_seal.json"
SEALED_FIELDS = (
    "id",
    "family",
    "report",
    "expected_top_cause",
    "answers",
    "source_url",
    "root_cause_status",
    "confirmation",
)


def build_seal() -> dict:
    report = build_report()
    if not report["test_ready"]:
        raise ValueError("冻结测试集尚未满足14类根因覆盖要求")

    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    split = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
    by_id = {case["id"]: case for case in cases}
    test_ids = split["frozen_test_ids"]
    payload = [
        {field: by_id[case_id][field] for field in SEALED_FIELDS}
        for case_id in test_ids
    ]
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "seal_id": "debugpath-frozen-test-v1",
        "split_version": split["version"],
        "case_count": len(payload),
        "cause_count": len({case["expected_top_cause"] for case in payload}),
        "source_overlap_with_development": report["source_overlap"],
        "sealed_fields": list(SEALED_FIELDS),
        "case_ids": test_ids,
        "content_sha256": hashlib.sha256(canonical).hexdigest(),
        "policy": "首次正式评测后不得修改本测试集；模型若更新，必须建立新版本和新的未见测试集。",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="写入当前冻结测试集指纹")
    args = parser.parse_args()
    current = build_seal()
    if args.write:
        SEAL_PATH.write_text(
            json.dumps(current, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"已封存{current['case_count']}条测试案例：{current['content_sha256']}")
        return
    if not SEAL_PATH.exists():
        raise SystemExit("尚未生成封存文件，请先运行 --write")
    saved = json.loads(SEAL_PATH.read_text(encoding="utf-8"))
    if current != saved:
        raise SystemExit("冻结测试集封存校验失败：内容或清单已变化")
    print(f"冻结测试集封存校验通过：{current['content_sha256']}")


if __name__ == "__main__":
    main()
