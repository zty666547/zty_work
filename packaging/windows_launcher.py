"""DebugPath Windows 单文件版本入口。"""
from __future__ import annotations

import multiprocessing
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

# 必须在导入应用配置之前固定便携版环境，避免读取用户机器上的私人配置。
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["ANSWER_MODE"] = "offline"
os.environ["DEMO_PLATFORM"] = "windows"
os.environ["DEBUGPATH_PACKAGED"] = "1"

# 让 PyInstaller 在分析阶段发现网页及其项目依赖。
import app as _debugpath_app  # noqa: F401,E402
from streamlit.web import cli as streamlit_cli  # noqa: E402


def bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def choose_port() -> int:
    requested = os.getenv("DEBUGPATH_PORT")
    candidates = [int(requested)] if requested else range(8501, 8600)
    for port in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("没有可用的本地端口，请关闭其他网页服务后重试。")


def open_browser(url: str) -> None:
    timer = threading.Timer(1.5, lambda: webbrowser.open(url, new=1))
    timer.daemon = True
    timer.start()


def main() -> int:
    root = bundle_root()
    os.chdir(root)
    port = choose_port()
    url = f"http://127.0.0.1:{port}"
    open_browser(url)
    sys.argv = [
        "streamlit",
        "run",
        str(root / "app.py"),
        "--server.headless=true",
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--server.fileWatcherType=none",
        "--browser.gatherUsageStats=false",
        "--global.developmentMode=false",
    ]
    return int(streamlit_cli.main() or 0)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
