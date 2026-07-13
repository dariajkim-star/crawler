# 공고 스코어링 + 노이즈 필터
# 점수 = 직군 가중치×10 + 스킬 매칭 가점 + 워치리스트 가점 + 신규 가점 + 마감 임박 가점

import re
from datetime import datetime, timedelta

from config import WATCHLIST, MY_SKILLS, CATEGORY_WEIGHTS, EXCLUDE_TITLE_KEYWORDS


def is_noise(title):
    """제목에 제외 키워드가 있으면 노이즈로 판정"""
    t = str(title).lower()
    return any(x.lower() in t for x in EXCLUDE_TITLE_KEYWORDS)


def is_watchlist(company):
    """관심 회사 여부 (부분일치)"""
    c = str(company).lower()
    return any(w.lower() in c for w in WATCHLIST)


def matched_skills(text):
    """텍스트에 포함된 내 스킬 키워드 목록"""
    t = str(text).lower()
    return [s for s in MY_SKILLS if s.lower() in t]


def parse_deadline(s):
    """마감일 문자열 -> datetime. 형식: '2026-09-06' | '~ 07/24(금)' | 빈칸"""
    s = str(s)
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', s)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r'(\d{2})/(\d{2})', s)
    if m:
        # 연도가 없는 형식(사람인) -> 올해로 가정, 이미 두 달 넘게 지났으면 내년
        d = datetime(datetime.now().year, int(m.group(1)), int(m.group(2)))
        if d < datetime.now() - timedelta(days=60):
            d = d.replace(year=d.year + 1)
        return d
    return None


def score_job(row, is_new=False):
    """공고 1건 점수화 -> (점수, 워치리스트여부, 제목매칭스킬)"""
    title = row.get("공고 이름", "")

    score = CATEGORY_WEIGHTS.get(row.get("직군", ""), 1) * 10

    skills = matched_skills(title)
    score += 5 * len(skills)

    watch = is_watchlist(row.get("회사 이름", ""))
    if watch:
        score += 30

    if is_new:
        score += 10

    deadline = parse_deadline(row.get("마감일", ""))
    if deadline:
        days_left = (deadline - datetime.now()).days
        if 0 <= days_left <= 3:
            score += 5  # 마감 임박

    return score, watch, skills
