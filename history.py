# 공고 이력 누적 DB (SQLite: jobs_history.db)
# - 매일 크롤링 결과를 upsert -> 언제 처음/마지막으로 봤는지, 몇 번 등장했는지 기록
# - 신규 공고 / 처음 보는 회사 / 반복 채용 회사 분석에 사용

import re
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "jobs_history.db"


def canonical_link(link):
    """사람인 링크의 검색어/세션 파라미터 제거 (rec_idx만 남김).
    과거 형식의 링크가 들어와도 같은 공고로 인식되게 함."""
    m = re.search(r'saramin\.co\.kr.+rec_idx=(\d+)', str(link))
    if m:
        return f"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={m.group(1)}"
    return str(link)

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    link       TEXT PRIMARY KEY,
    source     TEXT,   -- 출처
    category   TEXT,   -- 직군
    keyword    TEXT,   -- 검색어
    title      TEXT,   -- 공고 이름
    company    TEXT,   -- 회사 이름
    location   TEXT,   -- 회사 위치
    posted     TEXT,   -- 게시일
    deadline   TEXT,   -- 마감일
    first_seen TEXT,   -- 처음 수집된 날짜
    last_seen  TEXT,   -- 마지막으로 목록에 있던 날짜
    seen_count INTEGER DEFAULT 1  -- 등장한 수집 횟수
);
CREATE INDEX IF NOT EXISTS idx_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_first_seen ON jobs(first_seen);
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def ingest(df):
    """통합 DataFrame을 upsert.
    반환: (신규 공고 링크 set, 처음 보는 회사 set)"""
    today = time.strftime("%Y-%m-%d")
    conn = get_conn()
    cur = conn.cursor()

    known_companies = {r[0] for r in cur.execute("SELECT DISTINCT company FROM jobs")}

    new_links, new_companies = set(), set()
    for _, r in df.iterrows():
        link = canonical_link(r.get("링크", ""))
        if not link:
            continue
        exists = cur.execute("SELECT 1 FROM jobs WHERE link=?", (link,)).fetchone()
        if exists:
            cur.execute("UPDATE jobs SET last_seen=?, seen_count=seen_count+1 WHERE link=?",
                        (today, link))
        else:
            company = r.get("회사 이름", "")
            cur.execute(
                "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,1)",
                (link, r.get("출처", ""), r.get("직군", ""), r.get("검색어", ""),
                 r.get("공고 이름", ""), company, r.get("회사 위치", ""),
                 r.get("게시일", ""), r.get("마감일", ""), today, today))
            new_links.add(link)
            if company and company not in known_companies:
                new_companies.add(company)

    conn.commit()
    conn.close()
    return new_links, new_companies


def repeat_companies(days=30, limit=15):
    """최근 N일 동안 공고를 많이 낸 회사 (상시 채용 시그널)"""
    since = time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))
    conn = get_conn()
    rows = conn.execute("""
        SELECT company, COUNT(*) AS cnt, COUNT(DISTINCT category) AS cats
        FROM jobs
        WHERE last_seen >= ? AND company != ''
        GROUP BY company ORDER BY cnt DESC LIMIT ?""", (since, limit)).fetchall()
    conn.close()
    return rows


def new_companies_since(days=7, limit=20):
    """최근 N일 사이 처음 등장한 회사와 대표 공고"""
    since = time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))
    conn = get_conn()
    rows = conn.execute("""
        SELECT company, MIN(first_seen), COUNT(*), MAX(title), MAX(link)
        FROM jobs
        WHERE company != '' AND company NOT IN (
            SELECT DISTINCT company FROM jobs WHERE first_seen < ?
        )
        GROUP BY company
        HAVING MIN(first_seen) >= ?
        ORDER BY MIN(first_seen) DESC LIMIT ?""", (since, since, limit)).fetchall()
    conn.close()
    return rows


def weekly_counts(days=7):
    """최근 N일 신규 공고 수 (직군별)"""
    since = time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))
    conn = get_conn()
    rows = conn.execute("""
        SELECT category, COUNT(*) FROM jobs
        WHERE first_seen >= ? GROUP BY category ORDER BY 2 DESC""", (since,)).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM jobs WHERE first_seen >= ?", (since,)).fetchone()[0]
    all_time = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    conn.close()
    return rows, total, all_time
