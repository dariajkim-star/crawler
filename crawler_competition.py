import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
from selenium import webdriver

import time
from tqdm import tqdm

max_pages = int(input('몇 페이지까지 크롤링할까요?\n '))
all_corpus = [] #1,2,3...max_pages까지 크롤링 내역을 저장하는 list

#tqdm이 전체 실행시간 대비, 현재진행상황을 알려줌
for page in tqdm(range(1, max_pages+1), desc='크롤링 진행중임'):
    
    url =f'https://www.cheongwon.go.kr/portal/petition/open/view?pageIndex={page}'

    response = requests.get(url)
    print(response)

    soup = BeautifulSoup(response.text, 'html.parser')
    #print(response.text) 

    category = soup.find_all('span', class_='category')
    subject = soup.find_all('span', class_='subject')
    petition = soup.find_all('span', class_='text')
    print(category, subject, petition)


    corpus = []
    for c, s, t  in zip(category, subject, petition):
        corpus.append([c.text,s.text,t.text])
    
    all_corpus.extend(corpus) #list라서 extend임. 
    time.sleep(2)

df = pd.DataFrame(all_corpus, columns=['category', 'subject', 'petition'])
print(df.head())

df.to_csv('./crawling_sample.csv', index=False, encoding='utf-8-sig')