"""全局配置。

配置来源优先级：
    1) 环境变量（读取 `<项目根>/.env`）
    2) 代码内默认值

统一从一个 `Settings` 对象读取，避免魔数散落在各模块。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from src.graph.schema import ENTITY_TYPES, RELATION_TYPES

# dotenv 为可选项：未安装时不会阻塞项目运行，只是不自动加载 .env
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

# 项目根目录：本文件位于 <root>/config/settings.py
ROOT_DIR = Path(__file__).resolve().parent.parent
if load_dotenv is not None:
    load_dotenv(ROOT_DIR / ".env")


# 可抽取的实体/关系类型（约束 DeepSeek 输出，避免自由发挥）
DEFAULT_ENTITY_TYPES = ENTITY_TYPES
DEFAULT_RELATION_TYPES = RELATION_TYPES


@dataclass
class Settings:
    """应用运行所需的全部可配置项。"""

    # --- 运行 ---
    app_env: str = "dev"
    answer_mode: str = "offline"  # offline | llm
    retrieval_strategy: str = "enhanced"  # baseline | enhanced

    # --- DeepSeek ---
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # --- Neo4j ---
    neo4j_uri: str = "neo4j://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "12345678"
    neo4j_database: str = "neo4j"

    # --- 抽取 ---
    extraction_mode: str = "structured"  # structured | llm
    entity_types: list[str] = field(default_factory=lambda: list(DEFAULT_ENTITY_TYPES))
    relation_types: list[str] = field(default_factory=lambda: list(DEFAULT_RELATION_TYPES))

    # --- 数据文件 ---
    structured_filename: str = "curriculum_structured.json"
    documents_filename: str = "curriculum_docs.txt"

    # --- 路径 ---
    raw_dir: Path = ROOT_DIR / "data" / "raw"
    processed_dir: Path = ROOT_DIR / "data" / "processed"
    kg_dir: Path = ROOT_DIR / "data" / "kg"

    @property
    def is_debug(self) -> bool:
        return self.app_env != "prod"


def _split_csv(value: str | None, default: list[str]) -> list[str]:
    """把 `a,b,c` 解析成列表；为空则回退默认值。"""
    if not value:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def load_settings() -> Settings:
    """从环境变量构建 Settings。"""
    return Settings(
        app_env=os.getenv("APP_ENV", "dev"),
        answer_mode=os.getenv("ANSWER_MODE", "offline"),
        retrieval_strategy=os.getenv("RETRIEVAL_STRATEGY", "enhanced"),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        neo4j_uri=os.getenv("NEO4J_URI", "neo4j://localhost:7687"),
        neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
        neo4j_password=os.getenv("NEO4J_PASSWORD", "12345678"),
        neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
        extraction_mode=os.getenv("EXTRACTION_MODE", "structured"),
        entity_types=_split_csv(os.getenv("ENTITY_TYPES"), DEFAULT_ENTITY_TYPES),
        relation_types=_split_csv(os.getenv("RELATION_TYPES"), DEFAULT_RELATION_TYPES),
        structured_filename=os.getenv(
            "STRUCTURED_FILENAME", "curriculum_structured.json"
        ),
        documents_filename=os.getenv("DOCUMENTS_FILENAME", "curriculum_docs.txt"),
    )


# 单例：全项目共享一套配置
settings = load_settings()
