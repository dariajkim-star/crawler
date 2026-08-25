# 고용24(work24.go.kr) 채용정보 크롤러
# 채용정보 검색 결과 페이지를 requests + BeautifulSoup으로 파싱
# 한 페이지 = 공고 10개 (currentPageNo/pageIndex로 페이징)

from bs4 import BeautifulSoup
import requests
import pandas as pd
import time
import re
from html import unescape
from tqdm import tqdm


def clean_text(text):
    if not text:
        return ""
    if hasattr(text, "get_text"):
        text = text.get_text()
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


BASE_URL = "https://www.work24.go.kr/wk/a/b/1200/retriveDtlEmpSrchList.do"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


def fetch_page(keyword, page, retries=3):
    """검색 결과 한 페이지의 html을 받아옴.
    타임아웃/비200 응답이면 점점 길게 쉬면서 재시도, 끝내 실패하면 None.
    (고용24의 '결과 끝'은 빈 목록으로 판정되므로 None은 항상 오류라는 뜻)"""
    params = {
        "searchMode": "Y",
        "siteClcd": "all",          #워크넷 + 민간사이트 전체
        "keyword": keyword,
        "srcKeyword": keyword,
        "termSearchGbn": "all",
        "keywordWantedTitle": "Y",  #공고 제목에서 검색
        "resultCnt": "10",
        "sortField": "DATE",        #최신순
        "sortOrderBy": "DESC",
        "currentPageNo": str(page),
        "pageIndex": str(page),
    }
    for attempt in range(retries):
        try:
            response = requests.get(BASE_URL, headers=HEADERS,
                                    params=params, timeout=15)
            if response.status_code == 200:
                return response.text
            print(f"[고용24] '{keyword}' p{page} HTTP {response.status_code} — 재시도 {attempt + 1}/{retries}", flush=True)
            time.sleep(5 * (attempt + 1))
        except requests.RequestException as e:
            print(f"[고용24] '{keyword}' p{page} 요청 실패({e.__class__.__name__}) — 재시도 {attempt + 1}/{retries}", flush=True)
            time.sleep(3 * (attempt + 1))
    return None


def parse_jobs(html, keyword):
    """tr[id^=list] 행에서 회사/제목/조건/위치/마감일을 뽑음"""
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    # 마감일은 행 옆의 <script> 안에 var date = '2026-09-06' 로 들어있음
    deadlines = re.findall(r"var date\s*=\s*'(\d{4}-\d{2}-\d{2})'", html)

    trs = soup.select("tr[id^=list]")
    for i, tr in enumerate(trs):
        company = clean_text(tr.select_one("a.cp_name"))
        title_a = tr.select_one("a.t3_sb")
        title = clean_text(title_a)
        link = ("https://www.work24.go.kr" + title_a.get("href", "")) if title_a else ""

        # 조건들: 연봉(li.dollar), 경력/학력(li.member), 근무형태(li.time), 위치(li.site)
        salary = clean_text(tr.select_one("li.dollar"))
        member = clean_text(tr.select_one("li.member"))
        worktime = clean_text(tr.select_one("li.time"))
        location = clean_text(tr.select_one("li.site"))

        deadline = deadlines[i] if i < len(deadlines) else ""

        if not title:
            continue

        rows.append({
            "검색어": keyword,
            "공고 이름": title,
            "회사 이름": company,
            "회사 위치": location,
            "연봉": salary,
            "경력/학력": member,
            "근무형태": worktime,
            "게시일": "",       #목록에 등록일이 없어서 비움
            "마감일": deadline,
            "링크": link,
        })
    return rows


def crawling_data(keyword, max_pages=10):
    all_rows = []
    for page in tqdm(range(1, max_pages + 1), desc=f"고용24 '{keyword}' 크롤링중"):
        html = fetch_page(keyword, page)
        if not html:
            #재시도까지 전부 실패한 오류 -> '결과 끝'과 다르므로 흔적을 남기고 중단
            print(f"[고용24] '{keyword}' {page}페이지에서 오류로 중단 (수집분 {len(all_rows)}건은 유지)", flush=True)
            break

        rows = parse_jobs(html, keyword)
        if not rows:
            break  #더 이상 결과 없음 (정상 종료)

        all_rows.extend(rows)
        time.sleep(2)  #예의는 국룰
    return all_rows


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

    df.to_csv("./work24_result.csv", index=False, encoding="utf-8-sig")
    df.to_json("./work24_result.json", orient="records", force_ascii=False, indent=2)
