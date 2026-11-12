# 대시보드 서버를 띄우되, 이미 떠 있으면 아무것도 하지 않는다.
#
# 작업 스케줄러가 매일 11:00에 이 스크립트를 부른다. server.py를 그냥 또 띄우면
# 8010 포트가 이미 잡혀 있어서 "address already in use"로 죽는다.
#
# 로그를 cmd의 '>>'로 받지 않고 파이썬이 직접 연다. cmd의 리다이렉션은 파일을
# 독점으로 열기 때문에, 서버가 떠 있는 동안 그 핸들을 계속 쥐고 있어서 다음날
# 런처가 같은 파일을 열지 못하고 출력 한 줄 없이 종료코드 1로 죽는다.
# 파이썬의 append 열기는 공유 모드라 이 문제가 없다.
#
# 수동 실행: python start_dashboard.py

import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
LOG_FILE = BASE_DIR / "logs" / "server.log"
HOST = "127.0.0.1"
PORT = 8010


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def already_running(timeout=1.0):
    """8010 포트에 누가 듣고 있으면 True."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((HOST, PORT)) == 0


def main():
    if already_running():
        log(f"대시보드가 이미 {HOST}:{PORT} 에서 실행 중 — 건너뜁니다")
        return 0

    log(f"대시보드 시작 → http://localhost:{PORT}")
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        code = subprocess.run([sys.executable, str(BASE_DIR / "server.py")],
                              cwd=BASE_DIR, stdout=f,
                              stderr=subprocess.STDOUT).returncode
    log(f"대시보드 종료 (코드 {code})")
    return code


if __name__ == "__main__":
    sys.exit(main())
