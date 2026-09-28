# 피플앤잡(peoplenjob.com) 외국계기업 채용공고 크롤러
# /jobs?page=N 목록을 requests + BeautifulSoup으로 파싱
# 한 페이지 = 공고 30개 (div.jd-card)
#
# 이 사이트는 keyword 파라미터를 무시하고 항상 같은 전체 목록을 돌려준다.
# 2026-09-28 확인: 'IBD' · '용접' · 'zzzqqqxyz'로 요청한 결과 30건이 링크까지 완전히 동일.
#
# 그래서 예전처럼 키워드마다 크롤링하면
#   1) 요청 41회가 전부 같은 목록을 받아 낭비되고
#   2) 첫 키워드(IBD)가 목록 전체를 선점한 뒤 나머지는 링크 중복 제거로 지워져
#      마케팅·구매·설계 같은 무관한 공고 300건이 전부 'IBD' 직군으로 오분류된다.
# 목록을 한 번만 받고, 직군은 검색어가 아니라 제목 매칭으로 판정한다.

from bs4 import BeautifulSoup
import requests
import pandas as pd
import time
import re
from html import unescape
from tqdm import tqdm
from datetime import datetime


def clean_text(text):
    if not text:
        return ""
    if hasattr(text, "get_text"):
        text = text.get_text()
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


BASE_URL = "https://www.peoplenjob.com/jobs"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


def canonical_link(href):
    """/jobs/6255971?keyword=... -> 검색어 파라미터 제거 (중복 제거 정확도 향상)"""
    m = re.search(r'peoplenjob\.com/jobs/(\d+)', str(href))
    if m:
        return f"https://www.peoplenjob.com/jobs/{m.group(1)}"
    return str(href).split("?")[0]


def parse_dates(meta_text):
    """'08.06 ~ 09.05' 형식 -> (게시일, 마감일) 'YYYY-MM-DD'. 연도는 올해로 가정"""
    year = datetime.now().year
    m = re.search(r'(\d{2})\.(\d{2})\s*~\s*(\d{2})\.(\d{2})', meta_text)
    if not m:
        # '08.06 ~' (상시채용 등 마감일 없음)
        m2 = re.search(r'(\d{2})\.(\d{2})\s*~', meta_text)
        if m2:
            return f"{year}-{m2.group(1)}-{m2.group(2)}", ""
        return "", ""
    posted = f"{year}-{m.group(1)}-{m.group(2)}"
    # 마감이 게시보다 앞이면 해를 넘긴 것 (12월 게시 -> 1월 마감)
    dl_year = year + 1 if m.group(3) < m.group(1) else year
    deadline = f"{dl_year}-{m.group(3)}-{m.group(4)}"
    return posted, deadline


def parse_jobs(html, keyword):
    """div.jd-card에서 제목/회사/위치/직급/게시일/마감일을 뽑음"""
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    for card in soup.select("div.jd-card"):
        title_a = card.select_one(".jd-card-title a")
        if not title_a:
            continue

        company = card.select_one(".jd-card-company")
        location = card.select_one(".jd-card-meta-location-text")
        career = card.select_one(".jd-card-meta-career-text")
        # 날짜는 '08.06 ~ 09.05' 형태로 meta-static 안에 있음
        meta_static = card.select_one(".jd-card-meta-static")
        posted, deadline = parse_dates(clean_text(meta_static))

        rows.append({
            "검색어": keyword,
            "공고 이름": clean_text(title_a),
            "회사 이름": clean_text(company),
            "회사 위치": clean_text(location),
            "경력": clean_text(career),
            "게시일": posted,
            "마감일": deadline,
            "링크": canonical_link(title_a.get("href", "")),
        })
    return rows


def fetch_page(keyword, page, retries=3):
    """검색 결과 한 페이지의 html을 받아옴.
    타임아웃/비200 응답이면 점점 길게 쉬면서 재시도, 끝내 실패하면 None."""
    for attempt in range(retries):
        try:
            response = requests.get(BASE_URL, headers=HEADERS,
                                    params={"keyword": keyword, "page": page},
                                    timeout=15)
            if response.status_code == 200:
                return response.text
            print(f"[피플앤잡] '{keyword}' p{page} HTTP {response.status_code} — 재시도 {attempt + 1}/{retries}", flush=True)
            time.sleep(5 * (attempt + 1))
        except requests.RequestException as e:
            print(f"[피플앤잡] '{keyword}' p{page} 요청 실패({e.__class__.__name__}) — 재시도 {attempt + 1}/{retries}", flush=True)
            time.sleep(3 * (attempt + 1))
    return None


# run_all이 이 플래그를 보고 키워드 반복 대신 목록 1회 수집으로 전환한다
SUPPORTS_KEYWORD_SEARCH = False


def match_keyword(title, keywords):
    """제목에 포함된 키워드 중 가장 구체적인(긴) 것을 반환. 없으면 빈 문자열.

    이 사이트는 검색이 안 되므로 직군 판정의 유일한 근거가 제목이다.
    단순 부분일치를 쓰면 'AI'가 hair · affairs · chain에 걸리므로
    단어 경계를 지키는 scoring.contains_term을 쓴다.
    """
    from scoring import contains_term

    hits = [k for k in keywords if contains_term(title, k)]
    return max(hits, key=len) if hits else ""


def crawling_data(keyword=None, max_pages=10):
    """전체 목록을 max_pages까지 수집. keyword 인자는 무시된다(사이트가 무시하므로).

    각 행의 '검색어'는 제목에 실제로 들어 있는 키워드로 채운다. 매칭되는 키워드가
    없으면 빈 문자열이고, run_all에서 직군 '기타'로 떨어져 점수가 낮게 매겨진다.
    """
    from config import ALL_KEYWORDS

    all_rows = []
    for page in tqdm(range(1, max_pages + 1), desc="피플앤잡 목록 크롤링중"):
        html = fetch_page("", page)
        if not html:
            #재시도까지 전부 실패한 오류 -> '결과 끝'과 다르므로 흔적을 남기고 중단
            print(f"[피플앤잡] {page}페이지에서 오류로 중단 (수집분 {len(all_rows)}건은 유지)", flush=True)
            break

        rows = parse_jobs(html, "")
        if not rows:
            break  # 더 이상 결과 없음 (정상 종료)

        all_rows.extend(rows)
        time.sleep(2)  # 예의는 국룰

    for r in all_rows:
        r["검색어"] = match_keyword(r.get("공고 이름", ""), ALL_KEYWORDS)
    hit = sum(1 for r in all_rows if r["검색어"])
    print(f"[피플앤잡] 목록 {len(all_rows)}건 중 키워드 매칭 {hit}건 (나머지는 직군 '기타')", flush=True)
    return all_rows


if __name__ == "__main__":
    from config import MAX_PAGES

    # 이 사이트는 검색이 안 되므로 키워드를 반복하지 않고 목록을 한 번만 받는다
    corpus = crawling_data(max_pages=MAX_PAGES)

    df = pd.DataFrame(corpus)
    if df.empty:
        print("수집된 공고 없음")
        raise SystemExit(0)
    df = df.drop_duplicates(subset=["링크"]).reset_index(drop=True)
    print(df.head())
    print(f"총 {len(df)}건 수집됨")

    df.to_csv("./peoplenjob_result.csv", index=False, encoding="utf-8-sig")
    df.to_json("./peoplenjob_result.json", orient="records", force_ascii=False, indent=2)
