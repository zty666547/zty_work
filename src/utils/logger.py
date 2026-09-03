"""日志工具：统一输出格式，区分文件日志与控制台。"""
from __future__ import annotations

import logging
import sys

_config_done = False


def get_logger(name: str = "kg_rag", level: int = logging.INFO) -> logging.Logger:
    """返回带统一格式的 logger。"""
    global _config_done
    if not _config_done:
        root = logging.getLogger()
        root.setLevel(level)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        root.addHandler(handler)
        _config_done = True
    return logging.getLogger(name)
