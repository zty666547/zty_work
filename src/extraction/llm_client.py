"""DeepSeek 大模型客户端封装。

DeepSeek API 兼容 OpenAI 协议，这里复用 `openai` SDK，统一处理：
    - 客户端初始化
    - 解析 JSON 输出（用于结构化抽取）
    - 问答生成（用于 RAG）
    - 网络/解析异常容错
"""
from __future__ import annotations

import json
import logging

from config.settings import Settings
from src.utils.logger import get_logger

logger = get_logger("kg_rag.llm")


class LLMClient:
    """面向 DeepSeek 的轻量封装。"""

    def __init__(self, settings: Settings):
        if not settings.deepseek_api_key or settings.deepseek_api_key.startswith("sk-xxxx"):
            raise RuntimeError("未检测到有效的 DEEPSEEK_API_KEY，请先在 .env 中配置。")
        from openai import OpenAI  # 延迟导入，避免无 key 时报 import 错误

        self._client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        self._model = settings.deepseek_model

    def chat(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        """普通文本生成，返回纯文本。"""
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = (resp.choices[0].message.content or "").strip()
        logger.info("LLM 调用完成，返回 %d 字符", len(text))
        return text

    def chat_json(self, system: str, user: str, temperature: float = 0.1) -> dict:
        """要求模型输出 JSON，并解析为字典；解析失败时尝试提取 JSON 片段。"""
        raw = self.chat(system, user, temperature=temperature, max_tokens=2000)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # 宽容处理：从文本中截取第一个 { ... }
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(raw[start : end + 1])
            logger.warning("模型输出不是合法 JSON，原样返回：%s", raw[:200])
            return {"raw": raw}
