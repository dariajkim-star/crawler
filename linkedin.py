# LinkedIn 채용공고 크롤러
# 로그인 없이 접근 가능한 LinkedIn 공개(게스트) API를 사용함
# https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
# 한 페이지 = 공고 25개 (start=0, 25, 50 ... 으로 페이징)
# 주의: 너무 빠르게 요청하면 429(요청 과다)가 뜸 -> time.sleep + 재시도로 예의있게 크롤링

from bs4 import BeautifulSoup
import requests
import pandas as pd
import time
import re
from html import unescape
from tqdm import tqdm

# saramin.py와 동일한 정제 함수 (문자열 버전)
def clean_text(text):
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


BASE_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


def fetch_page(keyword, start, location="South Korea", retries=3):
    """한 페이지(공고 25개)의 html을 받아옴. 429 뜨면 잠시 쉬었다가 재시도.
    반환: (html, 사유) — (None, "end")는 정상적인 결과 끝, (None, "error")는 오류로 포기."""
    params = {
        "keywords": keyword,
        "location": location,
        "start": start,
    }
    for attempt in range(retries):
        try:
            response = requests.get(BASE_URL, headers=HEADERS,
                                    params=params, timeout=10)
            # 200 정상 / 400 더 이상 페이지 없음 / 그 외(429 과다·403/999 봇차단·5xx)는 쉬었다 재시도
            if response.status_code == 200:
                return response.text, "ok"
            if response.status_code == 400:
                return None, "end"  # 결과 끝 (정상)
            print(f"[LinkedIn] '{keyword}' start={start} HTTP {response.status_code} — 재시도 {attempt + 1}/{retries}", flush=True)
            time.sleep(5 * (attempt + 1))  # 점점 길게 쉬기
        except requests.RequestException as e:
            print(f"[LinkedIn] '{keyword}' start={start} 요청 실패({e.__class__.__name__}) — 재시도 {attempt + 1}/{retries}", flush=True)
            time.sleep(3 * (attempt + 1))
    return None, "error"


def parse_jobs(html, keyword):
    """html에서 공고 카드(li)들을 뽑아서 dict 리스트로 반환"""
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    for card in soup.select("li"):
        title = card.select_one("h3.base-search-card__title")
        company = card.select_one("h4.base-search-card__subtitle")
        location = card.select_one("span.job-search-card__location")
        link = card.select_one("a.base-card__full-link")
        posted = card.select_one("time")

        # 제목 없는 li는 공고 카드가 아님
        if not title:
            continue

        rows.append({
            "검색어": keyword,
            "공고 이름": clean_text(title.get_text()),
            "회사 이름": clean_text(company.get_text() if company else ""),
            "회사 위치": clean_text(location.get_text() if location else ""),
            "게시일": posted.get("datetime", "") if posted else "",
            "링크": link.get("href", "").split("?")[0] if link else "",
        })
    return rows


def crawling_data(keyword, max_pages=10, location="South Korea"):
    """키워드 하나를 max_pages 페이지까지 크롤링"""
    all_rows = []
    for page in tqdm(range(max_pages), desc=f"'{keyword}' 크롤링중"):
        html, why = fetch_page(keyword, start=page * 25, location=location)
        if not html:
            if why == "error":
                #오류로 포기한 경우는 '결과 끝'과 다르므로 흔적을 남김
                print(f"[LinkedIn] '{keyword}' {page + 1}페이지에서 오류로 중단 (수집분 {len(all_rows)}건은 유지)", flush=True)
            break  # end면 더 이상 결과 없음 (정상 종료)

        rows = parse_jobs(html, keyword)
        if not rows:
            break

        all_rows.extend(rows)
        time.sleep(2)  # 예의는 국룰
    return all_rows


if __name__ == "__main__":
    # 키워드는 config.py에서 직군별로 관리
    from config import ALL_KEYWORDS, MAX_PAGES

    corpus = []
    for kw in ALL_KEYWORDS:
        corpus.extend(crawling_data(kw, max_pages=MAX_PAGES))

    df = pd.DataFrame(corpus)
    # 같은 공고가 여러 키워드에 걸리면 중복 -> 링크 기준으로 제거
    df = df.drop_duplicates(subset=["링크"]).reset_index(drop=True)
    print(df.head())
    print(f"총 {len(df)}건 수집됨")

    df.to_csv("./linkedin_result.csv", index=False, encoding="utf-8-sig")
    # 웹 대시보드(job_board.html)에서 읽을 수 있게 json으로도 저장
    df.to_json("./linkedin_result.json", orient="records", force_ascii=False, indent=2)
