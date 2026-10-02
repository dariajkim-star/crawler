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
import re
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

# 크롤링 시작 전 네트워크 연결 확인용. 실제 수집 대상 중 두 곳을 쓴다.
# 한 곳이 점검 중이어도 다른 곳으로 판정되도록 두 개를 둔다.
NET_CHECK_URLS = ("https://www.saramin.co.kr", "https://www.work24.go.kr")
NET_WAIT_MAX_SEC = 30 * 60  # 네트워크를 최대 30분까지 기다린다
NET_WAIT_INTERVAL = 30

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


def network_ready(timeout=5):
    """대상 사이트 중 한 곳이라도 응답하면 True.

    HTTP 상태 코드는 보지 않는다. 403이든 503이든 응답이 돌아왔다는 것 자체가
    연결은 살아 있다는 뜻이고, 여기서 판정하려는 건 그것뿐이다.
    """
    for url in NET_CHECK_URLS:
        try:
            requests.head(url, timeout=timeout, allow_redirects=True)
            return True
        except requests.RequestException:
            continue
    return False


def wait_for_network():
    """네트워크가 연결될 때까지 기다린다. 끝내 안 되면 False.

    16:00 예약 실행 시점에 와이파이가 끊겨 있는 일이 반복됐다.
      2026-09-30: 크롤링 내내 네트워크 없음 -> 전 소스 0건, 통합 파일 갱신 거부
      2026-10-01: 시작 19초 전 끊김, 6분 뒤 복구 -> 5,680건 (평소의 절반)
    크롤러가 키워드마다 하는 재시도는 30초 안에 소진되므로 그걸로는 못 버틴다.
    크롤링을 시작하기 전에 여기서 기다리는 편이 실패한 수집을 되돌리는 것보다 싸다.
    """
    if network_ready():
        return True

    log_run("네트워크 없음 — 연결을 기다립니다")
    waited = 0
    while waited < NET_WAIT_MAX_SEC:
        time.sleep(NET_WAIT_INTERVAL)
        waited += NET_WAIT_INTERVAL
        if network_ready():
            log_run(f"네트워크 복구 확인 ({waited // 60}분 {waited % 60}초 대기)")
            return True
    log_run(f"네트워크 대기 {NET_WAIT_MAX_SEC // 60}분 초과 — 크롤링을 건너뜁니다")
    return False


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


def release_single_run_lock():
    """잠금을 명시적으로 돌려준다 (잠금 보유 여부만 확인하고 빠질 때 사용)."""
    global _lock_fp
    if _lock_fp is None:
        return
    try:
        import msvcrt

        _lock_fp.seek(0)
        msvcrt.locking(_lock_fp.fileno(), msvcrt.LK_UNLCK, 1)
    except (ImportError, OSError):
        pass
    try:
        _lock_fp.close()
    except OSError:
        pass
    _lock_fp = None


def crawl_in_progress():
    """지금 다른 크롤링 프로세스가 돌고 있으면 True. 잡은 잠금은 즉시 돌려준다."""
    if not acquire_single_run_lock():
        return True
    release_single_run_lock()
    return False


def last_run_status():
    """crawl_history.log에서 마지막 '실행'의 (날짜, 상태)를 읽는다.

    상태는 '완료' | '실패' | '시작'(종료 기록 없이 끊김) 중 하나.
    '건너뜀'·'경고'는 실행이 아니므로 건너뛰고 더 거슬러 올라간다.
    """
    if not RUN_LOG.exists():
        return None, None
    try:
        lines = RUN_LOG.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None, None
    for line in reversed(lines):
        m = re.match(r"\[(\d{4}-\d{2}-\d{2}) [\d:]+\]\s*(\S+)", line)
        if not m:
            continue
        day, word = m.group(1), m.group(2)
        for state in ("완료", "실패", "시작"):
            if word.startswith(state):
                return day, state
    return None, None


def completed_today():
    """오늘 '완료'까지 간 실행이 있으면 True — 같은 날 이중 크롤링 방지.

    파일 수정 시각으로 판정하면, 부분 실패해서 망가진 결과물도 '오늘 갱신됨'으로
    보여 그날 재실행이 통째로 막힌다. 완주 성공 기록으로만 판정한다.
    """
    day, status = last_run_status()
    return status == "완료" and day == date.today().isoformat()


def report_interrupted_run():
    """직전 실행이 '시작'만 남기고 끊겼으면 기록하고 알린다.

    반드시 잠금을 잡은 뒤에 호출해야 한다. 잠금을 잡았다는 것은 지금 돌고 있는
    크롤링이 없다는 뜻이고, 그런데도 마지막 기록이 '시작'이면 직전 실행이
    절전·종료 등으로 죽은 것이다. 예전에는 이런 실행이 아무 흔적도 남기지 않았다.
    """
    day, status = last_run_status()
    if status != "시작":
        return
    msg = f"직전 실행({day})이 완료 기록 없이 중단됨 (PC 절전·종료 추정)"
    log_run("경고 — " + msg)
    send_slack(f":warning: *JobScope* {msg}")


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

    # 부분 실패를 알림에서 볼 수 있게 한다. 예전에는 41개 키워드 중 30개가 실패한
    # 실행과 완전 성공한 실행이 알림상 완전히 똑같아 보였다.
    dead = merged.attrs.get("dead_sources") or []
    failures = {k: v for k, v in (merged.attrs.get("failures") or {}).items() if v}
    if dead:
        lines.append(f":rotating_light: 수집 0건 소스: *{', '.join(dead)}* — 차단 의심")
    if failures:
        fail_txt = " · ".join(f"{k} {v}개" for k, v in failures.items())
        lines.append(f":warning: 실패한 키워드: {fail_txt}")

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
    return merged


if __name__ == "__main__":
    import sys

    dry = "--dry" in sys.argv
    if not dry:
        if not acquire_single_run_lock():
            log_run("건너뜀 — 다른 크롤링 프로세스가 이미 실행 중")
            sys.exit(0)
        # 잠금을 잡은 뒤에 확인해야 "돌고 있는 중"과 "죽은 채 방치됨"이 구분된다
        report_interrupted_run()
        if "--force" not in sys.argv and completed_today():
            log_run("건너뜀 — 오늘 이미 크롤링을 완주함 (--force 로 강제 실행 가능)")
            sys.exit(0)
        # 네트워크가 죽은 채로 시작하면 전 소스가 빈손으로 끝난다. 먼저 기다린다.
        if not wait_for_network():
            send_slack(":warning: *JobScope 크롤링 건너뜀*\n"
                       f"네트워크가 {NET_WAIT_MAX_SEC // 60}분 동안 연결되지 않았습니다. "
                       "다음 예약 시각에 다시 시도합니다.")
            sys.exit(0)

    log_run("시작" + (" (--dry)" if dry else ""))
    try:
        merged = main(dry=dry)
        log_run(f"완료 — {len(merged):,}건 저장" if merged is not None else "완료")
    except Exception:
        # 크롤링이 터져도 슬랙으로 알림
        err = traceback.format_exc()
        print(err)
        log_run("실패 — " + err.strip().splitlines()[-1][:200])
        send_slack(f":rotating_light: *JobScope 크롤링 실패*\n```{err[-500:]}```")
        raise
