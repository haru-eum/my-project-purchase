"""
run_all.py로 띄운 로컬 개발 서버를 종료한다.
"""

from __future__ import annotations

import json
import os
import signal
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
PID_FILE = ROOT_DIR / ".run_pids.json"


def _kill_pid(pid: int) -> bool:
    try:
        if os.name == "nt":
            # Windows에서 트리까지 강제 종료
            os.system(f"taskkill /PID {pid} /T /F >NUL 2>NUL")
        else:
            os.kill(pid, signal.SIGTERM)
        return True
    except OSError:
        return False


def main() -> int:
    if not PID_FILE.exists():
        print("[INFO] 실행 정보 파일이 없어 종료할 프로세스를 찾지 못했습니다.")
        return 0

    data = json.loads(PID_FILE.read_text(encoding="utf-8"))
    backend_pid = int(data.get("backend_pid", 0) or 0)
    frontend_pid = int(data.get("frontend_pid", 0) or 0)

    if backend_pid > 0:
        ok = _kill_pid(backend_pid)
        print(f"[OK] backend 종료 시도: pid={backend_pid} result={ok}")
    if frontend_pid > 0:
        ok = _kill_pid(frontend_pid)
        print(f"[OK] frontend 종료 시도: pid={frontend_pid} result={ok}")

    try:
        PID_FILE.unlink()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
