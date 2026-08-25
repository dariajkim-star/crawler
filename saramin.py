#소환문
from bs4 import BeautifulSoup  #정적인 크롤링
import requests
import pandas as pd
import time
import re #정규표현식 예쁘게~ 예쁘게~ 다듬기
from html import unescape #html 형식에서 깨진 글자 복원
from tqdm import tqdm

#크롤링 결과문 예쁘게 정제하는 중
#정제 1 : 깨진거 복원
def clean_text(text):
     #크롤링 했는데 text가 none
     if not text:
          return "" #예외처리

     # tag가 들어오면 안의 글자만 꺼냄
     if hasattr(text, "get_text"):
          text = text.get_text()

     text = unescape(text)
     # 정규표현식 : 텍스트를 특정한 패턴으로 찾아서 변형
     text = re.sub(r'\s+', ' ', text)
     #앞뒤공백은 따로 .strip()으로
     return text.strip()


HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        #요청하는 언어의 종류
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    }


BASE_URL = 'https://www.saramin.co.kr/zf_user/search'


def fetch_page(search_word, page, retries=3):
    """검색 결과 한 페이지의 html을 받아옴.
    타임아웃/차단(403·429)/서버 오류면 점점 길게 쉬면서 재시도, 끝내 실패하면 None."""
    for attempt in range(retries):
        try:
            #recruitPage=N 으로 페이지 넘김
            response = requests.get(BASE_URL, headers=HEADERS,
                                    params={'searchword': search_word,
                                            'recruitPage': page},
                                    timeout=10)
            if response.status_code == 200:
                return response.text
            #403/429(차단·과다 요청)·5xx: 빈 화면이 와도 조용히 넘어가지 말고 알리고 재시도
            print(f"[사람인] '{search_word}' p{page} HTTP {response.status_code} — 재시도 {attempt + 1}/{retries}", flush=True)
            time.sleep(5 * (attempt + 1))
        except requests.RequestException as e:
            print(f"[사람인] '{search_word}' p{page} 요청 실패({e.__class__.__name__}) — 재시도 {attempt + 1}/{retries}", flush=True)
            time.sleep(3 * (attempt + 1))
    return None


#깔끔한 정리를 위해 함수로 만듦
#검색어 + 페이지수를 변수로
def crawling_data(search_word, max_pages=10):

    rows = []

    for page in tqdm(range(1, max_pages + 1), desc=f"사람인 '{search_word}' 크롤링중"):

        html = fetch_page(search_word, page)
        if html is None:
            #재시도까지 전부 실패 -> 이 키워드는 여기서 멈추되, 지금까지 모은 rows는 살려서 반환
            print(f"[사람인] '{search_word}' {page}페이지에서 오류로 중단 (수집분 {len(rows)}건은 유지)", flush=True)
            break

        soup = BeautifulSoup(html, 'html.parser')
        items = soup.select('div.item_recruit')
        if not items:
            break  #더 이상 공고 없음

        for item_recruit in items:

            #1. 공고 제목 + 링크
            #링크에 검색어/세션 파라미터가 붙어서 같은 공고가 다른 링크로 보임
            #-> rec_idx만 남긴 정규화 링크로 저장 (중복 제거 정확도 향상)
            title_a = item_recruit.select_one('.job_tit a')
            title = clean_text(title_a)
            href = title_a.get('href', '') if title_a else ''
            m_idx = re.search(r'rec_idx=(\d+)', href)
            if m_idx:
                link = f'https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={m_idx.group(1)}'
            else:
                link = ('https://www.saramin.co.kr' + href) if href else ''

            #2. 회사명
            name = clean_text(item_recruit.select_one('div.area_corp .corp_name'))

            #3. 조건 (위치, 경력)
            condition = item_recruit.select_one('.job_condition')
            location = ''
            career = ''
            if condition:
                span = condition.select('span')
                if len(span) > 0:
                    location = span[0].get_text(strip=True)
                if len(span) > 1:
                    career = span[1].get_text(strip=True)

            #4. 직무분야 (끝에 "등록일 26/07/05"가 붙어 나옴 -> 게시일로 분리)
            job_sector = clean_text(item_recruit.select_one('.job_sector'))
            posted = ''
            m = re.search(r'(등록일|수정일)\s*(\d{2}/\d{2}/\d{2})', job_sector)
            if m:
                yy, mm, dd = m.group(2).split('/')
                posted = f'20{yy}-{mm}-{dd}'
                job_sector = job_sector[:m.start()].strip()

            #5. 마감일 (~ 07/24(금) 형식)
            deadline = clean_text(item_recruit.select_one('.job_date .date'))

            rows.append({
                "검색어": search_word,
                "공고 이름": title,
                "회사 이름": name,
                "회사 위치": clean_text(location),
                "경력": clean_text(career),
                "직무분야": job_sector,
                "게시일": posted,
                "마감일": deadline,
                "링크": link,
            })

        time.sleep(2)  #예의는 국룰

    return rows


#진입점: def로 묶은 함수가 실제로 실행되는 부분
if __name__ == '__main__':
    #키워드는 config.py에서 직군별로 관리
    from config import ALL_KEYWORDS, MAX_PAGES

    corpus = []
    for kw in ALL_KEYWORDS:
        #키워드 하나가 죽어도 그때까지 모은 corpus는 저장까지 가도록 보호
        try:
            corpus.extend(crawling_data(kw, max_pages=MAX_PAGES))
        except Exception as e:
            print(f"'{kw}' 크롤링 실패({e.__class__.__name__}: {e}) — 건너뛰고 계속", flush=True)

    df = pd.DataFrame(corpus)
    #같은 공고가 여러 키워드에 걸리면 중복 -> 링크 기준 제거
    df = df.drop_duplicates(subset=["링크"]).reset_index(drop=True)
    print(df.head())
    print(f"총 {len(df)}건 수집됨")

    df.to_csv('./saramin_result.csv', index=False, encoding='utf-8-sig')
    df.to_json('./saramin_result.json', orient='records', force_ascii=False, indent=2)
