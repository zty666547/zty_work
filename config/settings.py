"""DebugPath 全局配置。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from src.graph.schema import ENTITY_TYPES, RELATION_TYPES

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

ROOT_DIR = Path(__file__).resolve().parent.parent
if load_dotenv is not None:
    load_dotenv(ROOT_DIR / ".env")


@dataclass
class Settings:
    app_env: str = "dev"
    answer_mode: str = "offline"  # offline | llm
    platform: str = "macos"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    neo4j_uri: str = "neo4j://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "12345678"
    neo4j_database: str = "neo4j"
    extraction_mode: str = "structured"
    entity_types: list[str] = field(default_factory=lambda: list(ENTITY_TYPES))
    relation_types: list[str] = field(default_factory=lambda: list(RELATION_TYPES))
    structured_filename: str = "debugpath_knowledge.json"
    documents_filename: str = "debugpath_docs.txt"
    confidence_threshold: float = 0.78
    max_questions: int = 4
    min_information_gain: float = 0.01
    raw_dir: Path = ROOT_DIR / "data" / "raw"
    processed_dir: Path = ROOT_DIR / "data" / "processed"
    kg_dir: Path = ROOT_DIR / "data" / "kg"

    @property
    def is_debug(self) -> bool:
        return self.app_env != "prod"


def load_settings() -> Settings:
    return Settings(
        app_env=os.getenv("APP_ENV", "dev"),
        answer_mode=os.getenv("ANSWER_MODE", "offline"),
        platform=os.getenv("DEMO_PLATFORM", "macos"),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        neo4j_uri=os.getenv("NEO4J_URI", "neo4j://localhost:7687"),
        neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
        neo4j_password=os.getenv("NEO4J_PASSWORD", "12345678"),
        neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
        extraction_mode=os.getenv("EXTRACTION_MODE", "structured"),
        structured_filename=os.getenv("STRUCTURED_FILENAME", "debugpath_knowledge.json"),
        documents_filename=os.getenv("DOCUMENTS_FILENAME", "debugpath_docs.txt"),
        confidence_threshold=float(os.getenv("CONFIDENCE_THRESHOLD", "0.78")),
        max_questions=int(os.getenv("MAX_QUESTIONS", "4")),
        min_information_gain=float(os.getenv("MIN_INFORMATION_GAIN", "0.01")),
    )

settings = load_settings()
