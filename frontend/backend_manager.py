"""
後端服務自動管理模組
當 Streamlit 前端啟動時，自動檢測並啟動 Redis / Celery / FastAPI。
前端關閉時，自動清理由本模組啟動的 process。
支援自動 port 分配：若預設 port 被其他專案佔用，自動尋找可用 port。
"""
import atexit
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests

_fastapi_process = None
_started_by_us = False
_workdir = None
_active_port = None  # 實際使用的 port

DEFAULT_PORT = 8000
PORT_RANGE = (8000, 8099)  # 搜尋範圍
LOCK_FILE_NAME = "logs/backend.lock"


def is_backend_running(port: int) -> bool:
    """檢查本專案的後端是否已在指定 port 運行"""
    try:
        r = requests.get(f"http://localhost:{port}/api/v1/llm/providers", timeout=2)
        return r.status_code == 200 and isinstance(r.json(), list)
    except Exception:
        return False


def is_port_available(port: int) -> bool:
    """檢查 port 是否可用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) != 0


def find_free_port() -> int:
    """在 PORT_RANGE 範圍內找到第一個可用 port"""
    for port in range(PORT_RANGE[0], PORT_RANGE[1] + 1):
        if is_port_available(port):
            return port
    raise RuntimeError(f"Port {PORT_RANGE[0]}-{PORT_RANGE[1]} 全部被佔用")


def _is_redis_running() -> bool:
    """檢查 Redis 是否在運行"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", 6379)) == 0


def start_redis() -> bool:
    """啟動 Redis（若未運行）"""
    if _is_redis_running():
        return True
    try:
        subprocess.run(
            ["brew", "services", "start", "redis"],
            capture_output=True, timeout=10,
        )
        time.sleep(1)
        if _is_redis_running():
            return True
    except Exception:
        pass
    try:
        subprocess.Popen(
            ["redis-server", "--daemonize", "yes"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(1)
        return _is_redis_running()
    except Exception:
        return False


def start_celery(workdir: str) -> bool:
    """啟動 Celery worker"""
    log_dir = Path(workdir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    pid_file = log_dir / "celery.pid"

    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            return True
        except (OSError, ValueError):
            pid_file.unlink(missing_ok=True)

    try:
        subprocess.Popen(
            [
                sys.executable, "-m", "celery",
                "-A", "src.celery_app", "worker",
                "--loglevel=info",
                f"--logfile={log_dir / 'celery.log'}",
                f"--pidfile={pid_file}",
                "--detach",
            ],
            cwd=workdir,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(2)
        return pid_file.exists()
    except Exception:
        return False


def start_fastapi(workdir: str, port: int) -> bool:
    """啟動 FastAPI 服務到指定 port"""
    global _fastapi_process

    log_dir = Path(workdir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = open(log_dir / "fastapi.log", "a")

    _fastapi_process = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "src.api.main:app",
            "--host", "0.0.0.0",
            "--port", str(port),
        ],
        cwd=workdir,
        stdout=log_file, stderr=log_file,
    )

    for _ in range(15):
        time.sleep(1)
        if is_backend_running(port):
            return True
        if _fastapi_process.poll() is not None:
            return False
    return False


def _write_lock(workdir: str, port: int):
    """寫入 lock file（含 port 資訊）"""
    lock = Path(workdir) / LOCK_FILE_NAME
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({
        "pid": os.getpid(),
        "port": port,
        "fastapi_pid": _fastapi_process.pid if _fastapi_process else None,
    }))


def _read_lock(workdir: str) -> dict | None:
    """讀取 lock file"""
    lock = Path(workdir) / LOCK_FILE_NAME
    if not lock.exists():
        return None
    try:
        data = json.loads(lock.read_text())
        os.kill(data["pid"], 0)  # 管理者 process 還活著嗎
        return data
    except (OSError, json.JSONDecodeError, KeyError):
        lock.unlink(missing_ok=True)
        return None


def get_active_port() -> int:
    """取得目前後端實際使用的 port"""
    return _active_port or DEFAULT_PORT


def ensure_backend(workdir: str) -> tuple:
    """
    確保後端服務正在運行。
    Returns: (success: bool, message: str)
    成功時可透過 get_active_port() 取得實際 port。
    """
    global _started_by_us, _workdir, _active_port
    _workdir = workdir

    # 1. 檢查 lock file — 看之前是否已啟動在某個 port
    lock_data = _read_lock(workdir)
    if lock_data and "port" in lock_data:
        port = lock_data["port"]
        if is_backend_running(port):
            _active_port = port
            return (True, f"後端已在運行 (port {port})")

    # 2. 掃描常用 port 範圍，看本專案後端是否已在某個 port 運行
    for port in range(PORT_RANGE[0], PORT_RANGE[1] + 1):
        if is_backend_running(port):
            _active_port = port
            return (True, f"後端已在運行 (port {port})")

    # 3. 需要啟動 — 找一個可用 port
    try:
        port = find_free_port()
    except RuntimeError as e:
        return (False, str(e))

    _started_by_us = True

    if not start_redis():
        return (False, "Redis 啟動失敗，請手動執行 redis-server")

    start_celery(workdir)

    if not start_fastapi(workdir, port):
        return (False, "FastAPI 啟動失敗，請查看 logs/fastapi.log")

    _active_port = port
    _write_lock(workdir, port)

    if port != DEFAULT_PORT:
        return (True, f"後端服務已自動啟動 (port {port}，因 {DEFAULT_PORT} 被佔用)")
    return (True, "後端服務已自動啟動")


def cleanup_backend():
    """清理由本模組啟動的 process"""
    global _fastapi_process, _started_by_us

    if not _started_by_us:
        return

    if _fastapi_process and _fastapi_process.poll() is None:
        _fastapi_process.terminate()
        try:
            _fastapi_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _fastapi_process.kill()
        _fastapi_process = None

    if _workdir:
        pid_file = Path(_workdir) / "logs" / "celery.pid"
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, signal.SIGTERM)
            except (OSError, ValueError):
                pass

        lock = Path(_workdir) / LOCK_FILE_NAME
        lock.unlink(missing_ok=True)

    _started_by_us = False


# 註冊清理函式
atexit.register(cleanup_backend)

try:
    import threading
    if threading.current_thread() is threading.main_thread():
        def _signal_handler(signum, frame):
            cleanup_backend()
            sys.exit(0)
        signal.signal(signal.SIGTERM, _signal_handler)
except Exception:
    pass
