#소환문
from bs4 import BeautifulSoup  #정적인 크롤링
import requests
import pandas as pd
import time
import re #정규표현식 예쁘게~ 예쁘게~ 다듬기
from html import unescape #html 형식에서 깨진 글자 복원

#크롤링 결과문 예쁘게 정제하는 중
#정제 1 : 깨진거 복원
def clean_text(text):
     #크롤링 했는데 text가 none
     if not text:
          return " " #예외처리 
     
     # text가 있다면 정제
     text = unescape(text.text)
     # 정규표현식 : 텍스트를 특정한 패턴으로 찾아서 변형
     #re.sub(패턴, 바꿀문자, 문장) : 패턴 -> 바꿀문자
     #\s, tab , entre는 다 공백임
     #\s 공백 \s+ 한칸 이상의 공백
     #문장 내의 모든 공백 한칸이상의 공백을 한칸짜리 공백으로 만드는걸 text에 적용해서 text에 담아줘
     text = re.sub(r'\s+', ' ', text)
     #앞뒤공백은 따로 .strip()으로
     return text.strip()



#깔끔한 정리를 위해 함수로 만듦
#검색어를 변수로 만들려고 param 건들임
def crawling_data(search_word):
      

    #크롤링의 순서
    #1. base_url 주소 가져오기
    #2. requests.get(base_url) '주소'에 있는 html 받아옴
    #3. bs4 받아온 html을 파싱 (필요정보 추출)
    #4. bs4_selcet(구분자), bs4.select_one
    #구분자 <div><div>
    #5.얻어낸 정보를 re(정규표현식)으로 정제 후 pandas로 저장


    #1. base_url가져오기
    base_url = 'https://www.saramin.co.kr/zf_user/search'

    #headers는 브라우저가 서버에 무언가를 요청할 때 '나 이런 브라우저다'라는 내용
    headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            #요청하는 언어의 종류
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        }


    #2. requests.get(base_url) '주소'에 있는 html 받아옴
    #headers: 웹페이지에 정보요청하는 브라우저에 대한 내용
    #param: 웹페이지에 이런 정보를 요청한다는 조건, 검색어. 
    #timeout: 웹페이지로부터 회신이 올 때까지 기다리는 시간 최대치.  
    response = requests.get(base_url, headers=headers, 
                            params={'searchword': search_word}, 
                                    timeout=10)


    #3. bs4 받아온 html을 파싱 (필요정보 추출)
    #만약 response가 <200>이면 정상-> 파싱, <400><500> 대단히 문제 큼.
    # <400> 서버에러 = 정보를 주는 웹페이지. 이거뜨면 주소확인하고 기다림ing
    # <500> 클라이언트에러 = get()을 뭔가 잘못함. 
    # bs4에게 파싱하도록 객체 생성  
    soup = BeautifulSoup(response.text, 'html.parser')
    #print(response.text)


    #4. bs4_selcet(구분자), bs4.select_one
    rows = []
    #find_element는 전통적인 방식
    #select는 현대적인 방식
    #soup.select('구분자') : '구분자'가 붙은 모든 태그를 가져와서 list로 반환
    #soup.find_all('div', class_='item_recruit') 

    for item_recruit in soup.select('div.item_recruit'):
            #a-tag 찾기 1) 중복되는애 2) 큰 범주-> 작은 범주
            #a_tag = item_recruit.find('a')
            #1. 회사명          
            #select_one('구분자') : '구분자'가 붙은 첫번째 태그를 가져와서 반환
            name = item_recruit.select_one('div.area_corp')
            

            #2. 채용 정보
            info = item_recruit.select_one('div.area_job')
            

            #3. 공고 제목
            #<div>로 시작하지 않음 .job_tit
            title = item_recruit.select_one('.job_tit')
            

            #4. 조건 #쫌쫌따리가 많을 때
            condition = item_recruit.select_one('.job_condition')
            #초기화 (hox,,,y 모르니까)
            location = '' 
            condition1 = ''

            if condition :
                span =condition.select('span')
                if len(span) > 0:
                    #공고목록을 보니까 첫번째는 위치네
                    location = span[0].get_text(strip=True)
                
                if len(span) >1:
                    #목록을 보니까 두번째는 경력
                    condition1 = span[1].get_text(strip=True)

            condition = (str(condition).strip() if condition else "조건음슴")

        
                

            #5. 직무분야
            job_sector = info.select_one('.job_sector')
            job_sector = (job_sector.get_text(strip=True) if job_sector else "")

            #뽀드득 뽀드득 공백없이 깔끔하지롱
            #내가 모은 정보를 '정제'
            title = clean_text(title)
            location= clean_text(location)
            condition1 = clean_text(condition1)
            job_sector = clean_text(job_sector)
            name = clean_text(name)
    
            #row 리스트, 리스트 안에 dic -> pandas로 만들기 위해서 감싸주는거
            rows.append({
                "공고 이름": title,
                "회사 위치": location,
                "조건1": condition1,
                "조건2": job_sector,
                "회사 이름": name,
            })


    #df에 담아서 저장
    df = pd.DataFrame(rows)
    print (df)

#진입점: def로 묶은 함수가 실제로 실행되는 부분
if __name__ == '__main__':
     crawling_data('research')