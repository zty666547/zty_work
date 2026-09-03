"""Neo4j 连接管理与轻量封装。"""
from __future__ import annotations

from config.settings import Settings
from src.utils.logger import get_logger

logger = get_logger("kg_rag.neo4j")


class Neo4jClient:
    """封装 Neo4j 连接与会话，提供统一的 execute 入口。"""

    def __init__(self, settings: Settings):
        from neo4j import GraphDatabase

        self._driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        self._database = settings.neo4j_database
        self._settings = settings
        self.verify_connectivity()

    def verify_connectivity(self) -> None:
        """测试连接，失败时给出引导提示。"""
        try:
            self._driver.verify_connectivity()
            logger.info(
                "已连接 Neo4j：%s (db=%s)", self._settings.neo4j_uri, self._database
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("无法连接 Neo4j：%s", exc)
            logger.error(
                "请确认：1) Neo4j 已启动；2) .env 中 NEO4J_URI/USER/PASSWORD 正确；"
                "3) 用户名密码与数据库名匹配。可用 `docker compose up -d neo4j` 快速启动。"
            )
            raise

    def run(self, query: str, parameters: dict | None = None) -> list[dict]:
        """执行只读/写入语句并返回记录列表。"""
        with self._driver.session(database=self._database) as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def close(self) -> None:
        self._driver.close()
