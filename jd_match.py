# JD(공고 상세) 스킬 매칭
# 고득점/워치리스트 공고만 상세 페이지를 열어서 내 스킬 키워드가 몇 개 나오는지 확인
# (전체 공고에 돌리면 요청이 너무 많아지므로 선별 적용)

import time

import requests
from bs4 import BeautifulSoup

from config import MY_SKILLS

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


def fetch_detail_text(url):
    """상세 페이지 본문 텍스트. 실패하면 빈 문자열 (매칭 생략)"""
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return ""
        soup = BeautifulSoup(res.text, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        return soup.get_text(" ").lower()
    except requests.RequestException:
        return ""


def match_skills(url):
    """JD에서 발견된 내 스킬 목록. 상세를 못 열면 None"""
    text = fetch_detail_text(url)
    if not text:
        return None
    return [s for s in MY_SKILLS if s.lower() in text]


def enrich_rows(rows, limit=12, delay=1.5):
    """공고 리스트(dict)에 'JD매칭' 필드를 추가 (최대 limit건만)"""
    for row in rows[:limit]:
        skills = match_skills(row.get("링크", ""))
        row["JD매칭"] = skills  # None = 확인 실패, [] = 매칭 없음
        time.sleep(delay)  # 예의는 국룰
    return rows
