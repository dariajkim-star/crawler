import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
from selenium import webdriver

import time
from tqdm import tqdm


url ='https://www.cheongwon.go.kr/portal/petition/open/view?'

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

time.sleep(2)

df = pd.DataFrame(corpus, columns=['category', 'subject', 'petition'])
print(df.head())

df.to_csv('./crawling_sample.csv', index=False, encoding='utf-8-sig')