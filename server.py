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

BASE_DIR = Path(__file__).parent
LOG_FILE = BASE_DIR / "crawl_log.txt"

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
    """run_all.py를 서브프로세스로 실행 (출력은 crawl_log.txt에 기록)"""
    state.update(running=True,
                 started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                 finished_at=None, returncode=None)

    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "MAX_PAGES": str(pages)}
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        proc = subprocess.run([sys.executable, "run_all.py"],
                              cwd=BASE_DIR, env=env,
                              stdout=f, stderr=subprocess.STDOUT)

    state.update(running=False,
                 finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                 returncode=proc.returncode)


@app.post("/api/crawl")
def start_crawl(pages: int = 10):
    """버튼 한 번 -> 사람인 + 고용24 + LinkedIn 전부 크롤링"""
    if state["running"]:
        return JSONResponse({"ok": False, "message": "이미 크롤링이 돌고 있어요"},
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
