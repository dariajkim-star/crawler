# We Work Remotely (weworkremotely.com) 원격 채용공고 크롤러
# 검색 결과 페이지를 requests + BeautifulSoup으로 파싱
# 특징: 검색 결과가 한 페이지에 전부 나옴 (페이지네이션 없음) -> max_pages는 무시됨
# 광고 카드(listing-ad)가 섞여 있음 -> 날짜/링크가 없는 li는 걸러냄

from bs4 import BeautifulSoup
import requests
import pandas as pd
import time
import re
from html import unescape
from tqdm import tqdm
from datetime import datetime, timedelta


def clean_text(text):
    if not text:
        return ""
    if hasattr(text, "get_text"):
        text = text.get_text()
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


BASE_URL = "https://weworkremotely.com/remote-jobs/search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


def parse_posted(date_text):
    """'2d' / '15d' 같은 상대 날짜 -> 'YYYY-MM-DD' 절대 날짜"""
    m = re.match(r'(\d+)d', str(date_text).strip())
    if m:
        d = datetime.now() - timedelta(days=int(m.group(1)))
        return d.strftime("%Y-%m-%d")
    return ""


def parse_jobs(html, keyword):
    """li.new-listing-container 카드에서 제목/회사/위치/게시일을 뽑음"""
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    for li in soup.select("li.new-listing-container"):
        title = li.select_one(".new-listing__header__title__text")
        link_a = li.select_one("a[href^='/remote-jobs/']")
        date_p = li.select_one(".new-listing__header__icons__date")

        # 광고 카드는 제목/날짜가 없음 -> 스킵
        if not title or not link_a or not date_p:
            continue

        company = li.select_one(".new-listing__company-name")
        location = li.select_one(".new-listing__company-headquarters")
        # 카테고리 태그(Full-Time, Anywhere in the World 등)는 근무형태로 저장
        cats = [clean_text(c) for c in li.select(".new-listing__categories__category")]

        rows.append({
            "검색어": keyword,
            "공고 이름": clean_text(title),
            "회사 이름": clean_text(company),
            "회사 위치": clean_text(location) or "Remote",
            "근무형태": ", ".join(cats),
            "게시일": parse_posted(clean_text(date_p)),
            "마감일": "",  # 목록에 마감일 없음
            "링크": "https://weworkremotely.com" + link_a.get("href", ""),
        })
    return rows


def crawling_data(keyword, max_pages=10):
    """키워드 하나 크롤링. 검색 결과가 단일 페이지라 요청은 1번"""
    # tqdm은 다른 크롤러와 로그 형태를 맞추기 위한 1스텝 진행바
    for _ in tqdm(range(1), desc=f"WWR '{keyword}' 크롤링중"):
        try:
            response = requests.get(BASE_URL, headers=HEADERS,
                                    params={"term": keyword}, timeout=15)
            if response.status_code != 200:
                return []
            rows = parse_jobs(response.text, keyword)
        except requests.RequestException:
            return []
        time.sleep(2)  # 예의는 국룰
    return rows


if __name__ == "__main__":
    # 키워드는 config.py에서 직군별로 관리
    from config import ALL_KEYWORDS, MAX_PAGES

    corpus = []
    for kw in ALL_KEYWORDS:
        corpus.extend(crawling_data(kw, max_pages=MAX_PAGES))

    df = pd.DataFrame(corpus)
    df = df.drop_duplicates(subset=["링크"]).reset_index(drop=True)
    print(df.head())
    print(f"총 {len(df)}건 수집됨")

    df.to_csv("./weworkremotely_result.csv", index=False, encoding="utf-8-sig")
    df.to_json("./weworkremotely_result.json", orient="records", force_ascii=False, indent=2)
