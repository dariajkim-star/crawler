import requests
from bs4 import BeautifulSoup

#웹브라우저 통신
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

#시간, pandas
import time
import pandas as pd
from tqdm import tqdm

#브라우저의 옵션(크롬)
#동적으로 selenium을 기반으로 작업할 때 아래같은 규칙 적용
option = Options()
option.add_argument('--no-sandbox') #보안끄기
option.add_argument('--disable-dev-shm-usage') #공유메모리 끄기
option.add_argument('--disable-gpu') 
option.add_argument('--enable-unsafe-swiftshader') #gpu랑 세트

driver = webdriver.Chrome(options=option)


base_url = 'https://www.musinsa.com/category/001/goods?gf=A'
driver.get(base_url)
time.sleep(2)


#윈도우 스크롤 내리는 스크립트 추가
driver.execute_script("window.scrollTo(0, 20000)")
time.sleep(2)

#창에 보이는 아이템들을 가져와
#정적(bs4), 동적)(selenium).find_elements(By.구분자)
#html은 웹페이지 내용담당, CSS는 디자인 담당. 
#구분자 = 계속 반복되는 애 
items = driver.find_elements(By.CSS_SELECTOR, ".sc-bSFBcf.iEkOIH")

item_list = []
for item in items: 
    #일단 아래코드를 실행해
    try:
        #개별 상품에 대한 정보
        #find_element 작은 범위에서 데이터를 찾아오겠다. 
        #a태그가 붙은 ['이름']을 가진 것
        a_tag = item.find_element(By.CSS_SELECTOR, "a[data-original-price]")

        #상품명
        name = a_tag.get_attribute("aria-label")
        #예외처리 -> 크롤링은 뭐가 들어올지 몰라서 예외처리가 key
        #str(name) : name에 뭐가 들어오든지 str처리.
        #replace : "제거할 데이터" , ""
        #strip() : 공백제거
        name = (str(name).replace("상품상세로 이동 ", "").strip() if name else "이름음슴")


        #브랜드 이름
        brand = a_tag.get_attribute("data-brand-id")
        brand = (str(brand).strip() if brand else "브랜드음슴")


        #가격
        price = a_tag.get_attribute("data-price")       
        price = (str(price).strip() if price else "가격음슴")

        #상세페이지 
        #href = html reference라서 하이퍼링크임
        link = a_tag.get_attribute("href")
        link = (str(link).strip() if link else "링크음슴")  
        
        print (f''' 상품명: {name}, 
               브랜드: {brand}, 
               가격: {price}, 
               링크: {link}''')
        item_list.append({"상품명": name, "브랜드": brand, "가격": price, "링크": link})

    #에러발생시 이렇게 해
    except Exception as e:
        print(f"에러!!!!!!!!!!: {e}")


#드라이버 종료
driver.quit()

df = pd.DataFrame(item_list, columns=["상품명", "브랜드", "가격", "링크"])
df.to_csv('./musinsa_result.csv', index=False, encoding='utf-8-sig')