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


#깔끔한 정리를 위해 함수로 만듦
#검색어 + 페이지수를 변수로
def crawling_data(search_word, max_pages=10):

    base_url = 'https://www.saramin.co.kr/zf_user/search'
    rows = []

    for page in tqdm(range(1, max_pages + 1), desc=f"사람인 '{search_word}' 크롤링중"):

        #recruitPage=N 으로 페이지 넘김
        response = requests.get(base_url, headers=HEADERS,
                                params={'searchword': search_word,
                                        'recruitPage': page},
                                timeout=10)

        soup = BeautifulSoup(response.text, 'html.parser')
        items = soup.select('div.item_recruit')
        if not items:
            break  #더 이상 공고 없음

        for item_recruit in items:

            #1. 공고 제목 + 링크
            title_a = item_recruit.select_one('.job_tit a')
            title = clean_text(title_a)
            link = ('https://www.saramin.co.kr' + title_a.get('href')) if title_a else ''

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
    keywords = ["AI", "애널리스트", "데이터사이언스", "머신러닝", "ML", "SQL", "openCV"]

    corpus = []
    for kw in keywords:
        corpus.extend(crawling_data(kw, max_pages=10))

    df = pd.DataFrame(corpus)
    #같은 공고가 여러 키워드에 걸리면 중복 -> 링크 기준 제거
    df = df.drop_duplicates(subset=["링크"]).reset_index(drop=True)
    print(df.head())
    print(f"총 {len(df)}건 수집됨")

    df.to_csv('./saramin_result.csv', index=False, encoding='utf-8-sig')
    df.to_json('./saramin_result.json', orient='records', force_ascii=False, indent=2)
