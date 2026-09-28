# JobScope 대시보드 서버 (FastAPI)
# - job_board.html과 크롤링 결과 json을 서빙
# - 대시보드의 [전체 크롤링 실행] 버튼 -> POST /api/crawl 로 크롤러 3개 일괄 실행
#
# 실행: python server.py  ->  http://localhost:8010

import os
import sys
import subprocess
import threading
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from run_and_notify import acquire_single_run_lock, release_single_run_lock

BASE_DIR = Path(__file__).parent
# 작업 스케줄러가 쓰는 로그와 분리한다. 예전엔 crawl_log.txt를 "w"로 열어
# 주간 리포트가 남긴 기록까지 통째로 날렸다.
LOG_FILE = BASE_DIR / "logs" / "dashboard_crawl.log"

app = FastAPI(title="JobScope")


# html/json은 항상 최신 버전을 받아야 함 -> 브라우저 캐시 금지
# (캐시가 남아있으면 코드/데이터를 갱신해도 옛 화면이 보임)
@app.middleware("http")
async def no_cache(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".json")):
        response.headers["Cache-Control"] = "no-store"
    return response

# 크롤링 진행 상태 (서버 메모리에 하나만 유지)
state = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "returncode": None,
}


def run_crawl(pages):
    """run_all.py를 서브프로세스로 실행. 잠금은 호출한 쪽이 이미 잡아뒀다."""
    state.update(running=True,
                 started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                 finished_at=None, returncode=None)

    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "MAX_PAGES": str(pages)}
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            proc = subprocess.run([sys.executable, "run_all.py"],
                                  cwd=BASE_DIR, env=env,
                                  stdout=f, stderr=subprocess.STDOUT)
        returncode = proc.returncode
    finally:
        # 잠금을 확실히 돌려줘야 다음 스케줄 크롤링이 막히지 않는다
        release_single_run_lock()
        state.update(running=False,
                     finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    state.update(returncode=returncode)


@app.post("/api/crawl")
def start_crawl(pages: int = 10):
    """버튼 한 번 -> 전체 소스 크롤링.

    예전에는 run_all.py를 그냥 띄워서 동시 실행 잠금을 건너뛰었다. 스케줄 크롤링이
    도는 중에 버튼을 누르면 두 프로세스가 같은 CSV를 동시에 써서 결과가 섞였다.
    """
    if state["running"]:
        return JSONResponse({"ok": False, "message": "이미 크롤링이 돌고 있어요"},
                            status_code=409)

    if not acquire_single_run_lock():
        return JSONResponse(
            {"ok": False, "message": "스케줄 크롤링이 실행 중이라 지금은 시작할 수 없어요"},
            status_code=409)

    threading.Thread(target=run_crawl, args=(pages,), daemon=True).start()
    return {"ok": True, "message": f"크롤링 시작 (키워드당 최대 {pages}페이지)"}


@app.get("/api/crawl/status")
def crawl_status():
    """진행 상태 + 로그 마지막 줄 (대시보드가 3초마다 폴링)"""
    progress = ""
    if LOG_FILE.exists():
        text = LOG_FILE.read_text(encoding="utf-8", errors="ignore")
        # tqdm은 \r로 줄을 덮어쓰므로 \n으로 바꿔서 마지막 줄만 꺼냄
        lines = [l.strip() for l in text.replace("\r", "\n").splitlines() if l.strip()]
        if lines:
            progress = lines[-1]
    return {**state, "progress": progress}


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "job_board.html")


# 나머지 파일(job_board.html, all_jobs.json 등)은 정적으로 서빙
# (API 라우트가 먼저 매칭되고, 못 찾으면 여기로 옴)
app.mount("/", StaticFiles(directory=BASE_DIR), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8010)
