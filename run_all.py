"""
로컬 개발용 원클릭 실행 스크립트.

- backend: python main.py (port 8000)
- frontend: npm run dev (port 3000)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
PID_FILE = ROOT_DIR / ".run_pids.json"


def _spawn(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.Popen:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    # Windows에서 부모 종료와 분리해 서버가 유지되도록 새 프로세스 그룹 사용
    return subprocess.Popen(  # noqa: S603
        command,
        cwd=str(cwd),
        env=merged_env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )


def main() -> int:
    db_path = ROOT_DIR / "scm_dashboard.db"
    if not db_path.exists():
        print("[WARN] scm_dashboard.db가 없어 init_db.py를 먼저 실행합니다.")
        init_proc = subprocess.run([sys.executable, "init_db.py"], cwd=str(ROOT_DIR), check=False)
        if init_proc.returncode != 0:
            print("[ERROR] init_db.py 실행 실패로 중단합니다.")
            return init_proc.returncode

    backend_proc = _spawn(
        [sys.executable, "main.py"],
        BACKEND_DIR,
        env={"UVICORN_RELOAD": "1"},
    )
    time.sleep(1.0)
    if os.name == "nt":
        # Windows에서 npm.cmd 경로 이슈를 피하려고 cmd를 통해 실행한다.
        frontend_cmd = ["cmd", "/c", "npm", "run", "dev"]
    else:
        frontend_cmd = ["npm", "run", "dev"]
    frontend_proc = _spawn(frontend_cmd, FRONTEND_DIR)

    payload = {
        "backend_pid": backend_proc.pid,
        "frontend_pid": frontend_proc.pid,
        "started_at": int(time.time()),
    }
    PID_FILE.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    print("[OK] 서버를 시작했습니다.")
    print(f" - backend pid: {backend_proc.pid} (http://localhost:8000)")
    print(f" - frontend pid: {frontend_proc.pid} (http://localhost:3000)")
    print("[TIP] 종료는 `python stop_all.py`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
