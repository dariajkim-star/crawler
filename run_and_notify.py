# 매일 오후 4시 스케줄러가 실행하는 스크립트 (JobScope_Daily_Crawl_16)
# 1) 크롤링 -> 이력DB(jobs_history.db)에 적재 -> 신규 공고/신규 회사 계산
# 2) 스코어링 -> 워치리스트 신규 + 오늘의 Top 10을 슬랙으로 전송
# 3) Top 공고는 JD 상세를 열어 내 스킬 매칭까지 표시
#
# 테스트: python run_and_notify.py --dry  (크롤링 없이 기존 all_jobs.json으로 알림만)
#
# 슬랙 연동 설정 (둘 중 하나, 웹훅 우선):
#   방법 A. Incoming Webhook (권장 - 만료 없음)
#     1. https://api.slack.com/apps -> Create New App -> Incoming Webhooks 활성화
#     2. 알림 받을 채널을 골라 Webhook URL 발급
#     3. URL을 slack_webhook.txt 에 저장 (또는 환경변수 SLACK_WEBHOOK_URL)
#   방법 B. 사용자/봇 토큰 (chat.postMessage)
#     - slack_token.txt 1번째 줄: 토큰(xoxp/xoxb...), 2번째 줄(선택): 채널 ID
#     - 채널을 안 쓰면 본인 DM(나에게 보내기)으로 전송
#     - 주의: xoxe.xoxp 회전 토큰은 12시간 뒤 만료됨 -> 장기 운영은 웹훅 권장
#
# 수동 실행: python run_and_notify.py
# 같은 날 이미 완주한 실행이 있으면 건너뜀 (--force 로 강제 실행)
# 다른 크롤링 프로세스가 돌고 있으면 잠금에 걸려 즉시 종료 (동시 실행 방지)
#
# 로그
#   crawl_history.log : 실행 이력 한 줄 요약 (이 스크립트가 직접 기록, 동시 실행에 안전)
#   logs/daily_crawl.log : 스케줄러가 남기는 표준출력 전문 (작업별로 파일 분리)

import json
import os
import time
import traceback
from datetime import date, datetime
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent
os.chdir(BASE_DIR)  # 작업 스케줄러는 cwd가 System32라서 고정 필요

ALL_JOBS = BASE_DIR / "all_jobs.json"
WEBHOOK_FILE = BASE_DIR / "slack_webhook.txt"
TOKEN_FILE = BASE_DIR / "slack_token.txt"
RUN_LOG = BASE_DIR / "crawl_history.log"
LOCK_FILE = BASE_DIR / "run_and_notify.lock"

_lock_fp = None  # 잠금 핸들 — 프로세스가 끝날 때까지 살려둬야 한다


def log_run(msg):
    """실행 이력을 crawl_history.log에 한 줄로 남긴다.

    파이썬의 append 열기는 공유 모드라 여러 프로세스가 동시에 써도 실패하지 않는다.
    반면 cmd의 '>>' 리다이렉션은 파일을 독점으로 열기 때문에, 작업 여러 개가 같은
    로그 파일을 쓰도록 등록돼 있으면 늦게 연 쪽이 출력 한 줄 없이 종료코드 1로 죽는다.
    (2026-09-18 실제 사고: 보충 실행으로 작업 3개가 동시에 떠서 일일 크롤링 2개가 이렇게 죽음)
    """
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        with open(RUN_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # 로그 실패로 크롤링을 죽이지 않는다


def acquire_single_run_lock():
    """동시 실행 방지 잠금. 스케줄러 작업이 여러 개 등록돼 있어도 크롤링은 한 번만 돈다.

    잠금은 프로세스가 끝날 때 OS가 자동 해제하므로, 비정상 종료돼도 잠금이 남지 않는다.
    """
    global _lock_fp
    try:
        import msvcrt
    except ImportError:
        return True  # Windows가 아니면 잠금 생략
    try:
        fp = open(LOCK_FILE, "a+")
    except OSError:
        return True  # 잠금 파일을 못 열면 잠금 없이 진행
    try:
        fp.seek(0)
        msvcrt.locking(fp.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        fp.close()
        return False
    _lock_fp = fp
    return True


def already_ran_today():
    """all_jobs.json이 오늘 갱신됐으면 True — 같은 날 이중 크롤링 방지."""
    if not ALL_JOBS.exists():
        return False
    return datetime.fromtimestamp(ALL_JOBS.stat().st_mtime).date() == date.today()


def get_webhook_url():
    url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not url and WEBHOOK_FILE.exists():
        url = WEBHOOK_FILE.read_text(encoding="utf-8").strip()
    return url


def get_token_and_channel():
    """slack_token.txt: 1줄=토큰, 2줄(선택)=채널 ID. 채널 없으면 본인 DM."""
    if not TOKEN_FILE.exists():
        return "", ""
    lines = [l.strip() for l in TOKEN_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    token = lines[0] if lines else ""
    channel = lines[1] if len(lines) > 1 else ""
    if token and not channel:
        # 채널 미지정 -> 본인 user_id로 DM (나에게 보내기)
        res = requests.post("https://slack.com/api/auth.test",
                            headers={"Authorization": f"Bearer {token}"}, timeout=10).json()
        channel = res.get("user_id", "")
    return token, channel


def fmt_job(r, extra=""):
    """슬랙 한 줄 포맷: 제목(링크) — 회사 [직군]"""
    star = "⭐" if r.get("워치리스트") else ""
    return f"• {star}<{r['링크']}|{r['공고 이름'][:60]}> — {r['회사 이름']} [{r['직군']}]{extra}"


def send_slack(text):
    # 1순위: 웹훅 (만료 없음)
    url = get_webhook_url()
    if url:
        res = requests.post(url, json={"text": text}, timeout=10)
        print(f"슬랙 전송(웹훅): {res.status_code}")
        return res.status_code == 200

    # 2순위: 토큰 (chat.postMessage)
    token, channel = get_token_and_channel()
    if token and channel:
        res = requests.post("https://slack.com/api/chat.postMessage",
                            headers={"Authorization": f"Bearer {token}"},
                            json={"channel": channel, "text": text},
                            timeout=10).json()
        print(f"슬랙 전송(토큰): ok={res.get('ok')} error={res.get('error', '')}")
        return bool(res.get("ok"))

    print("슬랙 미설정 -> 알림 생략 (slack_webhook.txt 또는 slack_token.txt 필요)")
    return False


def main(dry=False):
    import pandas as pd

    import history
    import jd_match
    from scoring import score_job

    # 1. 크롤링 (--dry면 기존 all_jobs.json 재사용)
    if dry:
        merged = pd.read_json(ALL_JOBS)
    else:
        import run_all
        merged = run_all.main()

    # 2. 이력 DB 적재 -> 신규 공고/처음 보는 회사
    new_links, new_companies = history.ingest(merged)

    # 3. 스코어링 (신규 가점 포함해서 재계산)
    rows = []
    for _, r in merged.iterrows():
        row = r.to_dict()
        is_new = history.canonical_link(row.get("링크", "")) in new_links
        row["점수"], row["워치리스트"], _ = score_job(row, is_new=is_new)
        row["신규"] = is_new
        rows.append(row)

    watch_new = [r for r in rows if r["워치리스트"] and r["신규"]]
    top10 = sorted(rows, key=lambda r: r["점수"], reverse=True)[:10]

    # 4. Top 10만 JD 상세를 열어 내 스킬 매칭 확인
    jd_match.enrich_rows(top10, limit=10)

    # 5. 슬랙 메시지 구성
    per_source = merged["출처"].value_counts().to_dict()
    src_txt = " · ".join(f"{k} {v:,}" for k, v in per_source.items())

    lines = [
        f":briefcase: *JobScope 채용공고 수집 완료* ({time.strftime('%Y-%m-%d %H:%M')})",
        f"총 *{len(merged):,}건* ({src_txt}) · :new: 신규 *{len(new_links):,}건* · 처음 보는 회사 *{len(new_companies):,}곳*",
    ]

    if watch_new:
        lines.append(f"\n:star: *관심 회사 신규 공고 {len(watch_new)}건*")
        for r in sorted(watch_new, key=lambda x: x["점수"], reverse=True)[:5]:
            lines.append(fmt_job(r))
        if len(watch_new) > 5:
            lines.append(f"…외 {len(watch_new)-5}건")

    lines.append("\n:trophy: *오늘의 Top 10* (직군·스킬·워치리스트·신규·마감 종합점수)")
    for r in top10:
        jd = r.get("JD매칭")
        extra = f" `{r['점수']}점`"
        if jd:
            extra += f" (JD매칭: {', '.join(jd[:5])})"
        lines.append(fmt_job(r, extra))

    lines.append("\n대시보드 → http://localhost:8010")
    send_slack("\n".join(lines))


if __name__ == "__main__":
    import sys

    dry = "--dry" in sys.argv
    if not dry:
        if not acquire_single_run_lock():
            log_run("건너뜀 — 다른 크롤링 프로세스가 이미 실행 중")
            sys.exit(0)
        if "--force" not in sys.argv and already_ran_today():
            log_run("건너뜀 — 오늘 이미 크롤링을 완주함 (--force 로 강제 실행 가능)")
            sys.exit(0)

    log_run("시작" + (" (--dry)" if dry else ""))
    try:
        main(dry=dry)
        log_run("완료")
    except Exception:
        # 크롤링이 터져도 슬랙으로 알림
        err = traceback.format_exc()
        print(err)
        log_run("실패 — " + err.strip().splitlines()[-1][:200])
        send_slack(f":rotating_light: *JobScope 크롤링 실패*\n```{err[-500:]}```")
        raise
